import axios from 'axios';
import toast from 'react-hot-toast';

const API_URL = import.meta.env.VITE_API_URL || '';

export const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add JWT token to requests
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Handle errors globally
api.interceptors.response.use(
    (response) => response,
    (error) => {
        const status = error.response?.status;
        const message = error.response?.data?.detail || error.message || 'An unexpected error occurred';

        if (status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = '/login';
        } else if (status === 403) {
            toast.error(`Permission Denied: ${message}`);
        } else if (status === 404) {
            // Don't toast on 404s sometimes they are expected (like "check status")
            // But for now, let's toast if it's likely an action failure
            if (error.config.method !== 'get') {
                toast.error(`Not Found: ${message}`);
            }
        } else if (status >= 500) {
            toast.error(`Server Error: ${message}`);
        } else {
            // General error for other codes
            toast.error(message);
        }

        return Promise.reject(error);
    }
);