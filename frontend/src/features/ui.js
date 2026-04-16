import { createSlice } from "@reduxjs/toolkit"

/*
  Intiial state
*/
const initialState = {
    duration: '',
    mobileSidebarOpen: false,
    currentSession: {
        chatId: null,
        chatName: ""
    }
}

const uiSlice = createSlice({
    name: 'ui',
    initialState,
    reducers: {
        changeSessionName(state, action) {
            state.currentSession = action.payload
        },
        clearSession: (state) => {
            state.currentSession = null;
        },
    }
})

export const { changeSessionName, clearSession } = uiSlice.actions

export default uiSlice.reducer;