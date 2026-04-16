import React, { lazy, Suspense } from "react";
import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { Provider } from "react-redux";
import store from "./store";
import MainAppLayout from "./layouts/MainAppLayout";
import { ContextProvider } from "./features/ContextProvider";

import Help from "./pages/Help";
import AboutPage from "./pages/About";
const Home = lazy(() => import("./pages/Home"));
const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));
const Recipes = lazy(() => import("./pages/Recipes"));
const RecipeDetail = lazy(() => import("./pages/RecipeDetail"));
const ForkEditor = lazy(() => import("./pages/ForkEditor"));
const ProfileDashboard = lazy(() => import("./pages/ProfileDashboard"));
const ActivateAccount = lazy(() => import("./pages/ActivateAccount"));
const LegalPage = lazy(() => import("./pages/LegalPage"));
const RecipeCreate = lazy(() => import("./pages/RecipeCreation"));

function App() {
  const publicRoutes = [
    { index: true, path: "/", element: <Home /> },
    { path: "/register", element: <Register /> },
    { path: "/login", element: <Login /> },
    { path: "/legal/:policyKey?", element: <LegalPage /> },
    { path: "/recipes", element: <Recipes /> },
    { path: "/recipes/:id", element: <RecipeDetail /> },
    { path: "/recipes/:id/fork", element: <ForkEditor /> },
    { path: "/recipes/create", element: <RecipeCreate /> },
    { path: "/profile", element: <ProfileDashboard /> },
    { path: "/profile/:username", element: <ProfileDashboard /> },
    { path: "/activate-account/*", element: <ActivateAccount /> },
    { path: "/help", element: <Help /> },
    { path: "/about", element: <AboutPage /> },
  ];

  const router = createBrowserRouter([
    {
      path: "/",
      element: (
        <ContextProvider>
          <MainAppLayout />
        </ContextProvider>
      ),
      children: publicRoutes,
    },
  ]);

  return (
    <Provider store={store}>
      <Suspense fallback={null}>
        <RouterProvider future={{ v7_startTransition: true }} router={router} />
      </Suspense>
    </Provider>
  );
}

export default App;
