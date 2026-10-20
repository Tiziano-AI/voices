import React from 'react';
import ReactDOM from 'react-dom/client';

import App from './App';
import './styles.css';

const root = document.getElementById('root');

if (root === null) {
  throw new Error('Unable to mount Voices web studio: #root is missing.');
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
