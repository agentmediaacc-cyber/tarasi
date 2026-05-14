const buttons = document.querySelectorAll(".control-strip button");
const cards = document.querySelectorAll(".route-card");

buttons.forEach((btn) => {
  btn.addEventListener("click", () => {
    buttons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");

    const filter = btn.dataset.filter;

    cards.forEach((card) => {
      const category = (card.dataset.category || "").toLowerCase();
      card.style.display = filter === "all" || category.includes(filter) ? "" : "none";
    });
  });
});
