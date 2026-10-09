// Leonida Wire: contador de dias até o lançamento e filtro de notícias.
(function () {
  var el = document.querySelector(".countdown");
  if (el) {
    var release = new Date((el.getAttribute("data-release") || "2026-11-19") + "T00:00:00-03:00");
    var days = Math.max(0, Math.ceil((release - new Date()) / 86400000));
    document.querySelectorAll("#cd-days, .js-days").forEach(function (n) { n.textContent = days; });
  }
  var chips = document.querySelectorAll(".chip");
  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var tag = chip.getAttribute("data-tag");
      chips.forEach(function (c) { c.setAttribute("aria-pressed", c === chip ? "true" : "false"); });
      document.querySelectorAll(".filterable > [data-tag]").forEach(function (item) {
        item.hidden = !!tag && item.getAttribute("data-tag") !== tag;
      });
    });
  });
})();
