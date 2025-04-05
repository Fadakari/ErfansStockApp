// theme.js
const root = document.documentElement;
const themeIcon = document.getElementById("themeIcon");

function setDarkMode() {
    root.style.setProperty("--black-color", "#1C1C1E");
    root.style.setProperty("--dark-green", "#3A3A3C");
    root.style.setProperty("--light-green", "#9B1B30");
    root.style.setProperty("--light-white", "#f1f1f1");
    root.style.setProperty("--txt-color", "#F8F8F8");
    if (themeIcon) {
        themeIcon.classList.remove("bi-brightness-high");
        themeIcon.classList.add("bi-moon");
    }
    localStorage.setItem("theme", "dark");
}

function setLightMode() {
    root.style.setProperty("--black-color", "#F8F8F8");
    root.style.setProperty("--dark-green", "#E0E0E0");
    root.style.setProperty("--light-green", "#9B1B30");
    root.style.setProperty("--light-white", "#F1F1F1");
    root.style.setProperty("--txt-color", "#1C1C1E");
    if (themeIcon) {
        themeIcon.classList.remove("bi-moon");
        themeIcon.classList.add("bi-brightness-high");
    }
    localStorage.setItem("theme", "light");
}

function loadTheme() {
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "dark") {
        setDarkMode();
    } else {
        setLightMode();
    }
}

// اجرا هنگام بارگذاری صفحه
document.addEventListener("DOMContentLoaded", () => {
    loadTheme();

    const toggleButton = document.getElementById("toggleButton");
    if (toggleButton) {
        toggleButton.addEventListener("click", () => {
            const currentTheme = localStorage.getItem("theme");
            if (currentTheme === "light") {
                setDarkMode();
            } else {
                setLightMode();
            }
        });
    }
});
