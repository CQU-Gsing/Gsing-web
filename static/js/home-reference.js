"use strict";
document.getElementById("year").textContent = new Date().getFullYear();
const account = document.querySelector(".account");
document.addEventListener("click", (event) => { if (account && !account.contains(event.target)) account.open = false; });
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && account?.open) { account.open = false; account.querySelector("summary").focus(); } });
const backToTop = document.getElementById("backToTopBtn");
function updateBackToTop(){ backToTop.hidden = window.scrollY < 300; }
window.addEventListener("scroll", updateBackToTop, {passive:true});
updateBackToTop();
backToTop.addEventListener("click", () => window.scrollTo({top:0,behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"instant":"smooth"}));
