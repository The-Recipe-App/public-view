import { createContext, useContext, useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

const AppContext = createContext();

export const ContextProvider = ({ children }) => {
    const [isLoading, setIsLoading] = useState(true);
    const [searchOpen, setSearchOpen] = useState(false);
    const [isAuthorized, setIsAuthorized] = useState(false);
    const [role, setRole] = useState(null);
    const [windowWidth, setWindowWidth] = useState(window.innerWidth);
    const [wantsToLogIn, setWantsToLogIn] = useState(false);
    const [wantsToRegister, setWantsToRegister] = useState(false);
    const [userName, setUserName] = useState("");
    const location = useLocation();
    const [recipes, setRecipes] = useState([]);
    const [wantsToActivateAccount, setWantsToActivateAccount] = useState(false);

    const isOverlay = windowWidth < 1024;

    const navigate = useNavigate();

    // useEffect(() => {
    //     const timer = setTimeout(() => setIsLoading(false), 8000);
    //     return () => clearTimeout(timer);
    // }, []);

    // const [pageTitle, setPageTitle] = useState("");

    // useEffect(() => {
    //     document.title = pageTitle;
    // }, [pageTitle]);

    useEffect(() => {
        if (location.pathname === "/login") {
            if (!isAuthorized) { 
                setWantsToLogIn(true);
            } else {
                setWantsToLogIn(false);
                navigate("/", { replace: true });
            }
        } else {
            setWantsToLogIn(false);
        }
    
        if (location.pathname === "/register") {
            setWantsToRegister(true);
        } else {
            setWantsToRegister(false);
        }
    
        if (location.pathname.startsWith("/activate-account")) {
            setWantsToActivateAccount(true);
        } else {
            setWantsToActivateAccount(false);
        }
    }, [location, isAuthorized, navigate]);

    useEffect(() => {
        const handleResize = () => {
            const screenWidth = window.innerWidth;
            setWindowWidth(screenWidth);
        };

        window.addEventListener("resize", handleResize);

        return () => {
            window.removeEventListener("resize", handleResize);
        };
    }, []);


    return (
        <AppContext.Provider value={{ isLoading, setIsLoading, /*setPageTitle,*/ isAuthorized, setIsAuthorized, role, setRole, windowWidth, wantsToLogIn, setWantsToLogIn, wantsToRegister, setWantsToRegister, recipes, setRecipes, userName, setUserName, wantsToActivateAccount, searchOpen, setSearchOpen, isOverlay }}>
            {children}
        </AppContext.Provider>
    );
};

export const useContextManager = () => useContext(AppContext);
