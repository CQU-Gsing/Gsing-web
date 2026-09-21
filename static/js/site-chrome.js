"use strict";
const headerMenus = [...document.querySelectorAll(".global-header details")];
headerMenus.forEach(menu => {
  menu.addEventListener("toggle", () => {
    if (menu.open) headerMenus.forEach(other => { if (other !== menu) other.open = false; });
  });
  menu.addEventListener("click", event => {
    if (event.target.closest("a")) menu.open = false;
  });
});
document.addEventListener("click", event => {
  headerMenus.forEach(menu => { if (!menu.contains(event.target)) menu.open = false; });
});
document.addEventListener("keydown", event => {
  if (event.key !== "Escape") return;
  const openMenu = headerMenus.find(menu => menu.open);
  if (openMenu) {
    openMenu.open = false;
    openMenu.querySelector("summary").focus();
  }
});
