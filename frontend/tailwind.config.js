/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    darkMode: 'class',
    theme: {
        extend: {
            colors: {
                canvas: 'var(--c-canvas)',
                panel: 'var(--c-panel)',
                'panel-2': 'var(--c-panel-2)',
                hairline: 'var(--c-hairline)',
                subtle: 'var(--c-subtle)',
                brand: {
                    DEFAULT: 'var(--c-brand)',
                    soft: 'var(--c-brand-soft)',
                    fg: 'var(--c-brand-fg)',
                },
            },
        },
    },
    plugins: [],
}