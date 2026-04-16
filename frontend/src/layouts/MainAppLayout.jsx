// MainAppLayout.jsx
import React, { useEffect, useState, useRef } from "react";
import { Toaster } from "react-hot-toast";
import { Outlet, useNavigate } from "react-router-dom";
import LoadingScreen from "../components/LoadingAnimation";
import { useContextManager } from "../features/ContextProvider";
import { motion, AnimatePresence } from "framer-motion";
import { useMe } from "../hooks/useMe";
import TopBar from "../components/TopBar";
import NavBar from "../components/NavBar";
import Footer from "../components/Footer";
import { lazy, Suspense } from "react";

const Login = lazy(() => import("../pages/Login"));
const Register = lazy(() => import("../pages/Register"));
const ActivateAccount = lazy(() => import("../pages/ActivateAccount"));

const MainAppLayout = () => {
    const { data: me, isLoading: meLoading, isError } = useMe();
    const { isLoading, setIsLoading, setIsAuthorized, isAuthorized, windowWidth, wantsToLogIn, setWantsToLogIn, wantsToRegister, wantsToActivateAccount, searchOpen, setSearchOpen, isOverlay } =
        useContextManager();

    const [navOpen, setNavOpen] = useState(windowWidth > 1024);
    const [shouldExitAnimation, setShouldExitAnimation] = useState(false);
    const navRef = useRef(null);
    const toggleBtnRef = useRef(null);

    const TOPBAR_HEIGHT = "3.7749rem";

    useEffect(() => {
        if (me) {
            setIsAuthorized(true);
        } else if (isError) {
            setIsAuthorized(false);
        }
        setIsLoading(meLoading);
    }, [me, isError, meLoading]);

    useEffect(() => {
        if (!localStorage.getItem("device_fp")) {
            const uuid = crypto.randomUUID?.() ??
                'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
                    const r = Math.random() * 16 | 0;
                    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
                });
            localStorage.setItem("device_fp", uuid);
        }

        const handleResize = () => {
            setNavOpen((prev) => (window.innerWidth > 1024 ? true : prev && window.innerWidth > 1024));
        };
        handleResize();
        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, []);

    useEffect(() => {
        setIsAuthorized(!!me);
    }, []);

    useEffect(() => {
        if (isLoading) {
            setShouldExitAnimation(false);
        }
    }, [isLoading]);


    return (
        <div className="min-h-screen flex flex-col bg-transparent relative overflow-hidden">
            <AnimatePresence>
                {!shouldExitAnimation && (
                    <motion.div
                        key="loader-overlay"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 z-50 pointer-events-auto"
                    >
                        <LoadingScreen isLoading={isLoading} shouldExit={shouldExitAnimation} setShouldExit={setShouldExitAnimation} />
                    </motion.div>
                )}
            </AnimatePresence>
            <Suspense fallback={null}>
                {wantsToActivateAccount ? (
                    <ActivateAccount />
                ) : wantsToLogIn ? (
                    <Login setIsAuthorized={setIsAuthorized} setIsLoading={setIsLoading} />
                ) : wantsToRegister ? (
                    <Register setWantsToLogIn={() => setWantsToLogIn(true)} />
                ) : (
                    <>
                        {/* TopBar spacer – prevents layout shift */}
                        <div style={{ height: TOPBAR_HEIGHT }} />

                        <TopBar
                            setIsAuthorized={setIsAuthorized}
                            toggleBtnRef={toggleBtnRef}
                            isAuthorized={isAuthorized}
                            windowWidth={windowWidth}
                            setNavOpen={setNavOpen}
                            navOpen={navOpen}
                            searchOpen={searchOpen}
                            setSearchOpen={setSearchOpen}
                        />

                        <div className="flex flex-1 relative">
                            {/* BACKDROP (overlay only) */}
                            {isOverlay && navOpen && (
                                <div className="fixed inset-0 bg-black/50 z-40" onClick={() => setNavOpen(false)} />
                            )}

                            {/* NAVBAR CONTAINER (animated inside NavBar now) */}
                            <div className={`${isOverlay ? "fixed inset-y-0 left-0 z-50" : "relative"} transition-all duration-300`}>
                                <NavBar
                                    setNavOpen={setNavOpen}
                                    isOpen={navOpen}
                                    isOverlay={isOverlay}
                                    navRef={navRef}
                                    onNavigate={() => isOverlay && setNavOpen(false)}
                                />
                            </div>

                            {/* MAIN CONTENT */}
                            <main className={`flex-1 transition-all duration-300 ${!isOverlay && navOpen ? "ml-[15rem]" : "ml-0"}`}>
                                <div>
                                    <Outlet />
                                </div>
                            </main>
                        </div>

                        {/* Toasts */}
                        <div className="absolute right-4 top-4 z-50">
                            <Toaster position="top-right" />
                        </div>

                        {/* Footer */}
                        {shouldExitAnimation && <Footer navOverlay={isOverlay} navOpen={navOpen} isAuthorized={isAuthorized} />}
                    </>
                )}
            </Suspense>
        </div>
    );
};

export default MainAppLayout;
