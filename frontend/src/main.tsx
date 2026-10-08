import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles/xiloscan.css';

const el = document.getElementById('root');
if (!el) throw new Error('#root não encontrado');
createRoot(el).render(<StrictMode><App /></StrictMode>);

// remove a splash assim que o app monta (com um tempo mínimo para não “piscar”)
const splash = document.getElementById('xs-splash');
if (splash) {
  const esconder = () => {
    splash.classList.add('hide');
    splash.addEventListener('transitionend', () => splash.remove(), { once: true });
    window.setTimeout(() => splash.remove(), 700);
  };
  window.setTimeout(esconder, 550);
}

// PWA: registra o service worker (instalável / shell offline). Só em produção
// e sob HTTPS/localhost — evita interferir no HMR do Vite em dev.
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* sem SW o app ainda funciona, só não fica offline */
    });
  });
}
