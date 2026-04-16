# Forkit Frontend 🍴

This is the frontend client for **Forkit**, a modern recipe discovery and community platform.

Built with:

- **React + JSX**
- **Vite**
- **TailwindCSS**
- **React Query**
- **Framer Motion**
- **Modern UI animations and responsive design**

---

## 🚀 Features

- Authentication (Login / Register / OTP Verification)
- User Profiles and Dashboards
- Recipe Feed and Discover Page
- Interactive UI with animations
- Fully responsive layout
- Fast API integration with backend services

---

## 📦 Tech Stack

| Tool | Purpose |
|------|---------|
| React | UI Framework |
| Vite | Development + Build Tooling |
| TypeScript | Type Safety |
| TailwindCSS | Styling System |
| React Query | API State + Caching |
| Axios | HTTP Client |
| Framer Motion | Animations |

---


### ⚠️ Important Notes

* Only variables prefixed with `VITE_` are exposed to the frontend.
* Never store private API keys in frontend `.env`.

---

## 🔌 Backend Connection

Forkit frontend connects to the FastAPI backend.

Make sure the backend is running at:

```
http://127.0.0.1:8000
```

---

## 📂 Project Structure

```bash
src/
  api/            # API services
  components/     # Shared reusable UI components
  pages/          # Main route pages
  hooks/          # Custom React hooks
  layouts/        # Page layout wrappers
  utils/          # Helpers and utilities
```

---

## 📜 Scripts

| Command           | Description              |
| ----------------- | ------------------------ |
| `npm run dev`     | Start development server |
| `npm run build`   | Build production bundle  |
| `npm run preview` | Preview production build |
| `npm run lint`    | Run ESLint checks        |

---

## 📄 License

This project is licensed under the AGPL License.

---

## ✨ Forkit

Made with love, by the Forkit Team.

```