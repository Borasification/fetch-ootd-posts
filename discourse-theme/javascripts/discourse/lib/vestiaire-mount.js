/*
 * Mounts the Vestiaire in a forum post.
 *
 * The post (written by `python -m ootd_awards story-post`) holds two blocks:
 *   [wrap=vestiaire]       where the card goes
 *   [wrap=vestiaire-data]  the page's data, zlib-compressed then base64-encoded,
 *                          in a code block
 * The card opens the story page full screen, over the forum.
 *
 * Forum content only ever goes through textContent.
 */
import "./ootd-story";

const FORMAT = "zlib-base64-v1";

export async function unpack(text) {
  const binary = atob(text.replace(/\s+/g, ""));
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate"));
  return JSON.parse(await new Response(stream).text());
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  });
  children.filter(Boolean).forEach((child) => node.append(child));
  return node;
}

const number = new Intl.NumberFormat("fr-FR");

// Light or dark, from the forum's own background colour
function forumScheme() {
  const rgb = getComputedStyle(document.body).backgroundColor.match(/\d+(\.\d+)?/g);
  if (!rgb) return "light";
  const luminance = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
  return luminance < 0.5 ? "dark" : "light";
}

function openOverlay(data, currentUser, opener) {
  const root = el("main", { class: "ootd-story" });
  const overlay = el("div", {
    class: "vs-overlay",
    role: "dialog",
    "aria-modal": "true",
    "aria-label": `Le vestiaire OOTD ${data.period.label}`,
  });

  function close() {
    document.removeEventListener("keydown", onKey);
    overlay.remove();
    document.documentElement.classList.remove("vs-overlay-open");
    opener?.focus();
  }

  function onKey(event) {
    // a photo opened in the lightbox closes first
    if (event.key === "Escape" && !overlay.querySelector("dialog[open]")) close();
  }

  const closeButton = el("button", {
    class: "vs-overlay__close",
    type: "button",
    text: "Fermer le vestiaire",
    onclick: close,
  });

  overlay.append(closeButton, root);
  document.body.append(overlay);
  document.documentElement.classList.add("vs-overlay-open");
  document.addEventListener("keydown", onKey);

  window.OotdStory.render(root, data, {
    currentUser,
    scroller: overlay,
    scheme: forumScheme(),
  });
  closeButton.focus({ preventScroll: true });
}

function teaser(anchor, data, currentUser) {
  const open = el("button", {
    class: "vs-teaser__open",
    type: "button",
    text: "Ouvrir le vestiaire",
  });
  open.addEventListener("click", () => openOverlay(data, currentUser, open));

  const prints = data.mosaic.slice(0, 5).map((src) => el("img", { src, alt: "", loading: "lazy", decoding: "async" }));
  anchor.replaceChildren(
    el("div", { class: "vs-teaser" }, [
      el("div", { class: "vs-teaser__prints", "aria-hidden": "true" }, prints),
      el("div", {}, [
        el("p", { class: "vs-teaser__title", text: `Le vestiaire OOTD ${data.period.label}` }),
        el("p", {
          class: "vs-teaser__stats",
          text: `${number.format(data.stats.outfits)} tenues, ${number.format(data.stats.members)} membres, `
            + `${number.format(data.stats.likes)} likes`,
        }),
      ]),
      open,
    ])
  );
}

function failed(anchor, message) {
  anchor.replaceChildren(
    el("div", { class: "vs-teaser vs-teaser--error" }, [el("p", { class: "vs-teaser__stats", text: message })])
  );
}

export function mountVestiaire(cooked, currentUser) {
  const anchor = cooked.querySelector('.d-wrap[data-wrap="vestiaire"]');
  const block = cooked.querySelector('.d-wrap[data-wrap="vestiaire-data"]');
  if (!anchor || anchor.dataset.vsMounted) return;
  anchor.dataset.vsMounted = "true";

  const code = block?.querySelector("code");
  if (!code) {
    failed(anchor, "Les données du vestiaire sont absentes de ce post.");
    return;
  }
  if (block.dataset.format && block.dataset.format !== FORMAT) {
    failed(anchor, "Ce vestiaire a été généré par une version plus récente : mets à jour le composant.");
    return;
  }
  if (!("DecompressionStream" in window)) {
    failed(anchor, "Ton navigateur est trop ancien pour afficher le vestiaire.");
    return;
  }

  unpack(code.textContent)
    .then((data) => teaser(anchor, data, currentUser))
    .catch(() => failed(anchor, "Les données du vestiaire sont illisibles : regénère le post."));
}
