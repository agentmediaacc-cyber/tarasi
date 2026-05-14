const buttons = document.querySelectorAll(".filters button");
const cards = document.querySelectorAll(".route-card");

buttons.forEach((btn) => {
  btn.addEventListener("click", () => {
    buttons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");

    const filter = btn.dataset.filter;

    cards.forEach((card) => {
      const category = card.dataset.category || "";
      const show = filter === "all" || category.includes(filter);
      card.style.display = show ? "" : "none";
    });
  });
});
