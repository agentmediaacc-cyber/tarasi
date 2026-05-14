document.querySelectorAll(".cat-card,.fleet-card,.experience-card,.route-row").forEach((card)=>{
  card.addEventListener("mousemove",(e)=>{
    const r = card.getBoundingClientRect();
    card.style.setProperty("--x", `${e.clientX - r.left}px`);
    card.style.setProperty("--y", `${e.clientY - r.top}px`);
  });
});
