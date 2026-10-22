document.addEventListener("DOMContentLoaded", () => {
  const s = document.querySelector('input[name="start_time"]');
  const e = document.querySelector('input[name="end_time"]');
  const h = document.querySelector('input[name="hours"]');
  if (!s || !e || !h) return;

  const calc = () => {
    if (!s.value || !e.value) return;
    const [sh, sm] = s.value.split(":").map(Number);
    const [eh, em] = e.value.split(":").map(Number);
    let mins = (eh * 60 + em) - (sh * 60 + sm);
    if (mins < 0) mins += 24 * 60;
    h.value = (mins / 60).toFixed(2);
  };
  s.addEventListener("change", calc);
  e.addEventListener("change", calc);
});