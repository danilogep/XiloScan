"""Testes do extrator ArcFace (rodam em CPU, sem download de pesos)."""
import pytest
import torch

from backend.app.model import (
    ArcMarginProduct,
    GeM,
    XiloArcFaceModel,
    XiloEmbedder,
    resolve_device,
)

DIM = 128


@pytest.fixture(scope="module")
def embedder():
    # pretrained=False evita baixar pesos no CI
    return XiloEmbedder("resnet18", embedding_dim=DIM, pretrained=False).eval()


def test_embedding_normalizado_e_com_dimensao_certa(embedder):
    x = torch.randn(2, 3, 128, 128)
    with torch.inference_mode():
        e = embedder(x)
    assert e.shape == (2, DIM)
    assert torch.allclose(e.norm(dim=1), torch.ones(2), atol=1e-5)


def test_embedder_deterministico_em_eval(embedder):
    x = torch.randn(1, 3, 128, 128)
    with torch.inference_mode():
        a, b = embedder(x), embedder(x)
    assert torch.allclose(a, b, atol=1e-6)


def test_imagens_parecidas_ficam_mais_proximas_que_ruido(embedder):
    torch.manual_seed(0)
    base = torch.randn(1, 3, 128, 128)
    quase = base + torch.randn_like(base) * 0.02
    outra = torch.randn(1, 3, 128, 128)
    with torch.inference_mode():
        e = embedder(torch.cat([base, quase, outra]))
    assert float(e[0] @ e[1]) > float(e[0] @ e[2])


def test_gem_entre_avg_e_max():
    x = torch.rand(2, 8, 6, 6)
    gem = GeM(p=3.0)
    out = gem(x)
    assert out.shape == (2, 8)
    avg = x.mean(dim=(2, 3))
    mx = x.amax(dim=(2, 3))
    assert torch.all(out >= avg - 1e-4) and torch.all(out <= mx + 1e-4)


def test_arcface_penaliza_a_classe_correta():
    """A margem deve reduzir o logit da classe verdadeira vs. cosseno puro."""
    torch.manual_seed(0)
    head = ArcMarginProduct(DIM, 5, scale=30.0, margin=0.30)
    emb = torch.nn.functional.normalize(torch.randn(4, DIM), dim=1)
    labels = torch.tensor([0, 1, 2, 3])
    logits = head(emb, labels)
    cos = torch.nn.functional.linear(
        emb, torch.nn.functional.normalize(head.weight)
    ) * head.scale
    alvo = logits[torch.arange(4), labels]
    alvo_cos = cos[torch.arange(4), labels]
    assert torch.all(alvo < alvo_cos)
    # os logits das outras classes ficam intactos
    assert torch.allclose(logits[0, 1:], cos[0, 1:], atol=1e-4)


def test_margem_zero_equivale_a_cosseno_escalado():
    head = ArcMarginProduct(DIM, 3, scale=1.0, margin=0.0)
    emb = torch.nn.functional.normalize(torch.randn(2, DIM), dim=1)
    labels = torch.tensor([0, 2])
    cos = torch.nn.functional.linear(emb, torch.nn.functional.normalize(head.weight))
    assert torch.allclose(head(emb, labels), cos, atol=1e-4)


def test_modelo_de_treino_devolve_embedding_e_logits():
    m = XiloArcFaceModel(n_classes=7, backbone="resnet18", embedding_dim=DIM, pretrained=False)
    m.embedder.backbone.reset_classifier(0, "")
    x = torch.randn(3, 3, 128, 128)
    y = torch.tensor([0, 3, 6])
    emb, logits = m(x, y)
    assert emb.shape == (3, DIM) and logits.shape == (3, 7)
    logits.sum().backward()
    assert m.head.weight.grad is not None


def test_forward_sem_labels_devolve_so_embedding():
    m = XiloArcFaceModel(n_classes=4, backbone="resnet18", embedding_dim=DIM, pretrained=False).eval()
    with torch.inference_mode():
        out = m(torch.randn(1, 3, 128, 128))
    assert out.shape == (1, DIM)


def test_resolve_device():
    assert resolve_device("cpu").type == "cpu"
    assert resolve_device("auto").type in {"cpu", "cuda", "mps"}
