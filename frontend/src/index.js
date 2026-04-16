import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { ContextProvider } from './features/ContextManager';

ReactDOM.createRoot(document.getElementById('root')).render(
    <React>
        <BrowserRouter>
            <ContextProvider>
                <App />
            </ContextProvider>
        </BrowserRouter>
    </React>
);

reportWebVitals();
