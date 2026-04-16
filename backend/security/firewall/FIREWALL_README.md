# Firewall Module

## Purpose
The Firewall module acts as the global request governor for the Forkit backend. It enforces rate limits, escalation, blocking, and audit logging for all incoming HTTP traffic.

## Flow

```mermaid
flowchart TD
    A[Request] --> B[Middleware]
    B --> C[Policy Resolver]
    C --> D[Rate Limit]
    D -->|Allowed| E[API Handler]
    D -->|Exceeded| F[Strike Engine]
    F --> G{Scope}
    G -->|Route| H[Temp Block]
    G -->|IP| H
    G -->|IP+FP| H
    G -->|Global| I[Permanent Ban]
    H --> J[Audit DB]
    I --> J
```

## Key Files
- middleware.py - Global FastAPI middleware
- rate_limit.py - Sliding window limiter
- strikes.py - In-memory strike counters
- strike_engine.py - Escalation logic
- blacklist.py - Active block lookup
