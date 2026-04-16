# Forkit Backend Architecture

## High-Level Flow

```mermaid
flowchart TD
    A[Client] --> B[FastAPI]
    B --> C[Firewall Middleware]
    C --> D[Policy Engine]
    D --> E[Rate Limiter]
    E --> F[Strike Engine]
    F --> G[Security DB]
    G --> H[API Routers]
    H --> I[Domain Services]
    I --> J[Database]
```

## Layers
- API Layer (FastAPI Routers)
- Security Layer (Firewall + Policies)
- Domain Layer (Ranking, Graph, Plans)
- Persistence Layer (Repositories + DB)
