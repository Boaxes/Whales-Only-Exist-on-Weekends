// Shared by the landing page and the six notebook pages.

// The portfolio case study this site belongs to: links marked data-portfolio="case" point to it, and
// data-portfolio="home" to the portfolio's front page. Served locally, they open the local portfolio.
const PORTFOLIO_CASE_STUDY = location.hostname === 'localhost'
  ? 'http://localhost:5190/portfolio/projects/whales'
  : 'https://brandonconnely.com/portfolio/projects/whales';

(function () {
  const home = new URL('/portfolio', PORTFOLIO_CASE_STUDY).href;

  function fillLinks() {
    document.querySelectorAll('a[data-portfolio]:not([href^="http"])').forEach((a) => {
      a.href = a.dataset.portfolio === 'home' ? home : PORTFOLIO_CASE_STUDY;
    });
  }

  let queued = false;
  function update() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; fillLinks(); });
  }

  document.addEventListener('DOMContentLoaded', () => {
    // (the links at once, not on the next frame: a tab opened in the background draws no frames)
    fillLinks();
    update();
    new MutationObserver(update).observe(document.body, { childList: true, subtree: true });
  });
})();
