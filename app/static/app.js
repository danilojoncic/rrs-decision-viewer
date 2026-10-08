const normalize = (value) =>
  value
    .toLowerCase()
    .replaceAll("ß", "ss")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\brrs\b/g, "")
    .replace(/[^a-z0-9]+/g, "");

const reviewMarkerToggle = document.querySelector("[data-review-marker-toggle]");

const reviewMarkerStorage = {
  get() {
    try {
      return globalThis.localStorage?.getItem("hideReviewMarkers") || null;
    } catch {
      return null;
    }
  },
  set(value) {
    try {
      globalThis.localStorage?.setItem("hideReviewMarkers", value);
    } catch {
      // The visual toggle still works for the current page if storage is unavailable.
    }
  },
};

const setReviewMarkersHidden = (hidden) => {
  document.body.classList.toggle("hide-review-markers", hidden);
  if (!reviewMarkerToggle) return;
  reviewMarkerToggle.setAttribute("aria-pressed", hidden ? "true" : "false");
  reviewMarkerToggle.textContent = hidden ? "Show Review Marks" : "Hide Review Marks";
};

setReviewMarkersHidden(reviewMarkerStorage.get() === "true");

reviewMarkerToggle?.addEventListener("click", () => {
  const hidden = !document.body.classList.contains("hide-review-markers");
  reviewMarkerStorage.set(hidden ? "true" : "false");
  setReviewMarkersHidden(hidden);
});

const closeFacetDropdown = (dropdown) => {
  const panel = dropdown.querySelector("[data-facet-panel]");
  const toggle = dropdown.querySelector("[data-facet-toggle]");
  if (!panel || !toggle) return;
  panel.hidden = true;
  toggle.setAttribute("aria-expanded", "false");
};

const openFacetDropdown = (dropdown) => {
  document.querySelectorAll("[data-facet-dropdown]").forEach((otherDropdown) => {
    if (otherDropdown !== dropdown) closeFacetDropdown(otherDropdown);
  });

  const panel = dropdown.querySelector("[data-facet-panel]");
  const toggle = dropdown.querySelector("[data-facet-toggle]");
  if (!panel || !toggle) return;
  panel.hidden = false;
  toggle.setAttribute("aria-expanded", "true");
  dropdown.querySelector("[data-facet-search]")?.focus();
};

document.querySelectorAll("[data-facet-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    const dropdown = button.closest("[data-facet-dropdown]");
    const panel = dropdown?.querySelector("[data-facet-panel]");
    if (!dropdown || !panel) return;

    if (panel.hidden) {
      openFacetDropdown(dropdown);
    } else {
      closeFacetDropdown(dropdown);
    }
  });
});

document.addEventListener("click", (event) => {
  document.querySelectorAll("[data-facet-dropdown]").forEach((dropdown) => {
    if (!dropdown.contains(event.target)) closeFacetDropdown(dropdown);
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll("[data-facet-dropdown]").forEach(closeFacetDropdown);
});

document.querySelectorAll("[data-facet-search]").forEach((input) => {
  const facetName = input.dataset.facetSearch;
  const options = document.querySelector(`[data-facet-options="${facetName}"]`);
  if (!options) return;

  input.addEventListener("input", () => {
    const query = normalize(input.value);
    options.querySelectorAll("label").forEach((label) => {
      const value = label.dataset.facetText || label.textContent || "";
      label.hidden = query && !normalize(value).includes(query);
    });
  });
});

document.querySelectorAll("[data-facet-clear]").forEach((button) => {
  button.addEventListener("click", () => {
    const facetName = button.dataset.facetClear;
    const panel = button.closest("[data-facet-panel]");
    panel?.querySelectorAll(`input[name="${facetName}"]`).forEach((checkbox) => {
      checkbox.checked = false;
    });
    panel?.querySelector("[data-facet-search]")?.focus();
  });
});

document.querySelectorAll("[data-open-section]").forEach((button) => {
  button.addEventListener("click", () => {
    const sectionName = button.dataset.openSection;
    document.querySelectorAll(".decision-section").forEach((section) => {
      section.open = section.dataset.section === sectionName;
    });
  });
});

document.querySelectorAll("[data-close-sections]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".decision-section").forEach((section) => {
      section.open = false;
    });
  });
});

document.querySelectorAll("[data-appendix-preset]").forEach((button) => {
  button.addEventListener("click", () => {
    const query = button.dataset.appendixPreset;
    window.location.href = query ? `/appendix-n?${query}` : "/appendix-n";
  });
});

document.querySelector("[data-appendix-preset-select]")?.addEventListener("change", (event) => {
  const query = event.target.value;
  if (query) window.location.href = `/appendix-n?${query}`;
});

document.querySelectorAll("[data-copy-text]").forEach((button) => {
  button.addEventListener("click", async () => {
    const originalText = button.textContent;
    const value = button.dataset.copyText || "";
    try {
      await navigator.clipboard.writeText(value);
      button.textContent = "Copied";
      setTimeout(() => {
        button.textContent = originalText;
      }, 1200);
    } catch {
      button.textContent = "Copy failed";
      setTimeout(() => {
        button.textContent = originalText;
      }, 1400);
    }
  });
});

const setFocusMode = (enabled) => {
  document.body.classList.toggle("case-focus-mode", enabled);
};

if (document.querySelector(".detail-page")?.dataset.focusStart === "true") {
  setFocusMode(true);
}

document.querySelector("[data-enter-fullscreen]")?.addEventListener("click", async () => {
  setFocusMode(true);
  try {
    if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
      await document.documentElement.requestFullscreen();
    }
  } catch {
    // CSS focus mode still works when browser fullscreen is unavailable.
  }
});

document.querySelector("[data-exit-fullscreen]")?.addEventListener("click", async () => {
  setFocusMode(false);
  try {
    if (document.fullscreenElement && document.exitFullscreen) {
      await document.exitFullscreen();
    }
  } catch {
    // The page-level exit is enough if browser fullscreen cannot be closed.
  }
  const url = new URL(window.location.href);
  url.searchParams.delete("focus");
  history.replaceState({}, "", url);
});

