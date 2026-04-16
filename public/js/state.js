// 共享狀態 — 所有模組透過此物件讀寫，避免全域變數污染
export const state = {
    hospitals: [],
    menuState: 'main',
    menuOptions: {},
    lastHospital: null,
    lastProgressData: [],
    pageItems: [],
    pageIndex: 0,
    pageContext: null,
    navStack: [],

    // 追蹤（最多 3 位）
    pendingTrack: null,
    tracks: [],
    waitingForNumber: false,

    // 用戶
    lineUserId: '',
    userFavorites: [],
    userArea: '',

    // 防重複點擊
    sending: false,
};

export const MAX_TRACKS = 3;
export const API_BASE = window.location.origin;
