(function () {
  "use strict";

  var MAX_RESULTS = 8;
  var script = document.currentScript;
  var scriptBase = script ? script.getAttribute("src").replace(/assets\/js\/search\.js.*$/, "") : "";
  var roots = document.querySelectorAll("[data-search-root]");

  if (!roots.length) {
    roots = Array.prototype.filter.call(document.querySelectorAll(".site-nav"), function (nav) {
      return nav.querySelector(".search-trigger") && nav.querySelector("[data-search-panel]");
    });
  }

  function normalize(value) {
    return (value || "").toString().toLowerCase().replace(/\s+/g, "");
  }

  function escapeHtml(value) {
    return (value || "").replace(/[&<>"']/g, function (char) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char];
    });
  }

  function fuzzyScore(value, query) {
    var lastIndex = -1;
    var penalty = 0;

    for (var i = 0; i < query.length; i += 1) {
      var index = value.indexOf(query[i], lastIndex + 1);
      if (index < 0) {
        return -1;
      }

      penalty += index - lastIndex - 1;
      lastIndex = index;
    }

    return Math.max(1, 260 - penalty - value.length / 100);
  }

  function scoreRecord(record, query) {
    var terms = record._terms;
    var slug = record._slug;
    var title = record._title;
    var url = record._url;

    if (!query) {
      return -1;
    }

    if (slug === query || title === query) {
      return 1000;
    }

    if (slug.indexOf(query) === 0) {
      return 900 - slug.length;
    }

    if (title.indexOf(query) === 0) {
      return 820 - title.length;
    }

    var slugIndex = slug.indexOf(query);
    if (slugIndex >= 0) {
      return 680 - slugIndex - slug.length / 100;
    }

    var titleIndex = title.indexOf(query);
    if (titleIndex >= 0) {
      return 600 - titleIndex - title.length / 100;
    }

    var urlIndex = url.indexOf(query);
    if (urlIndex >= 0) {
      return 500 - urlIndex;
    }

    return fuzzyScore(terms, query);
  }

  function prepareIndex(pages) {
    return pages.map(function (page) {
      var slug = page.slug || decodeURIComponent((page.url || "").replace(/^\/|\/$/g, ""));
      var title = page.title || slug || page.url;
      var url = page.url || "/";

      return {
        title: title,
        slug: slug,
        url: url,
        _title: normalize(title),
        _slug: normalize(slug),
        _url: normalize(url),
        _terms: normalize([title, slug, url].join(" "))
      };
    });
  }

  function getIndex(root) {
    if (window.__studyRouteSearchIndex) {
      return window.__studyRouteSearchIndex;
    }

    var indexUrl = root.getAttribute("data-search-index") || scriptBase + "search-index.json";
    window.__studyRouteSearchIndex = fetch(indexUrl, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Search index failed");
        }
        return response.json();
      })
      .then(function (payload) {
        return prepareIndex(payload.pages || []);
      })
      .catch(function () {
        return [];
      });

    return window.__studyRouteSearchIndex;
  }

  function init(root) {
    var toggle = root.querySelector("[data-search-toggle], .search-trigger");
    var close = root.querySelector("[data-search-close]");
    var input = root.querySelector("[data-search-input]");
    var results = root.querySelector("[data-search-results]");
    var panel = root.querySelector("[data-search-panel]");
    var indexPromise = null;

    if (!toggle || !input || !results || !panel) {
      return;
    }

    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-controls", panel.id || "site-search-panel");

    function render() {
      var query = normalize(input.value);

      if (!query) {
        results.innerHTML = '<p class="search-empty">Type a search term.</p>';
        return;
      }

      (indexPromise || getIndex(root)).then(function (index) {
        var matches = index
          .map(function (record) {
            return { record: record, score: scoreRecord(record, query) };
          })
          .filter(function (match) {
            return match.score > 0;
          })
          .sort(function (a, b) {
            return b.score - a.score || a.record.slug.length - b.record.slug.length;
          })
          .slice(0, MAX_RESULTS);

        if (!matches.length) {
          results.innerHTML = '<p class="search-empty">No results.</p>';
          return;
        }

        results.innerHTML = matches.map(function (match) {
          var record = match.record;
          return (
            '<a class="search-result" role="option" href="' + escapeHtml(record.url) + '">' +
            '<strong>' + escapeHtml(record.slug || record.title) + '</strong>' +
            '<span>' + escapeHtml(record.title) + '</span>' +
            '</a>'
          );
        }).join("");
      });
    }

    function openSearch() {
      root.classList.add("is-search-open");
      toggle.setAttribute("aria-expanded", "true");
      indexPromise = getIndex(root);
      window.setTimeout(function () {
        input.focus();
      }, 30);
      render();
    }

    function closeSearch() {
      root.classList.remove("is-search-open");
      toggle.setAttribute("aria-expanded", "false");
      input.value = "";
      results.innerHTML = "";
    }

    function toggleSearch() {
      if (root.classList.contains("is-search-open")) {
        closeSearch();
      } else {
        openSearch();
      }
    }

    toggle.addEventListener("click", toggleSearch);
    close.addEventListener("click", closeSearch);
    input.addEventListener("input", render);

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && root.classList.contains("is-search-open")) {
        closeSearch();
        toggle.focus();
      }
    });

    document.addEventListener("click", function (event) {
      if (root.classList.contains("is-search-open") && !root.contains(event.target)) {
        closeSearch();
      }
    });
  }

  Array.prototype.forEach.call(roots, init);
}());
