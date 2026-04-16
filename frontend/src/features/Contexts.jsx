import { createContext, useContext, useState } from "react";

// Create the context
const ContextPropsContext = createContext();

// Provider component
export function ContextPropsProvider({ children, initial = {} }) {
  const [contextProps, setContextProps] = useState(initial);
  return (
    <ContextPropsContext.Provider value={[contextProps, setContextProps]}>
      {children}
    </ContextPropsContext.Provider>
  );
}

// Hook to use the context
export function useContextProps() {
  return useContext(ContextPropsContext);
}
