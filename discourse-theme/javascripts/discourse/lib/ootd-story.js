/*
 * Vestiaire: renders the OOTD story page from the payload built by
 * ootd_awards/story.py. Vanilla JS, no dependency, so the same file can run
 * in the local preview and inside a Discourse theme component.
 *
 *   OotdStory.render(rootElement, payload, { currentUser, preview })
 *
 * options.scroller: the element that scrolls the page, when it runs inside a
 * full-screen overlay rather than the window (the Discourse theme component).
 * options.scheme: 'light' or 'dark', when the page cannot guess it from its parent.
 *
 * Forum content (usernames, captions) only ever goes through textContent.
 */
(function () {
  'use strict';

  var scroller = window;

  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var number = new Intl.NumberFormat('fr-FR');

  // ---------------------------------------------------------------- helpers

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key === 'style') Object.keys(value).forEach(function (p) { node.style.setProperty(p, value[p]); });
      else if (key.slice(0, 2) === 'on') node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    });
    (children || []).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    });
    return node;
  }

  function plural(n, one, many) { return number.format(n) + ' ' + (n > 1 ? many : one); }

  var MONTH_ABBR = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
                    'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];

  var SVG = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs, children) {
    var node = document.createElementNS(SVG, tag);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    (children || []).forEach(function (child) { node.appendChild(child); });
    return node;
  }

  // A shirt monogram: two initials for two words (JeanDupont, jean_dupont), else one
  function initials(name) {
    var parts = name.replace(/([\p{Ll}\p{N}])(\p{Lu})/gu, '$1 $2')
                    .replace(/[^\p{L}\p{N}]+/gu, ' ').trim().split(' ');
    return (parts.length > 1 ? parts[0][0] + parts[1][0] : parts[0][0]).toUpperCase();
  }

  // The member's profile picture in a stitched ring, or their monogram without one
  function portrait(name, avatar, large) {
    var cls = 'vs-monogram' + (avatar ? ' vs-monogram--photo' : '') + (large ? ' vs-monogram--large' : '');
    if (!avatar) return el('span', { class: cls, 'aria-hidden': 'true', text: initials(name) });
    return el('span', { class: cls, 'aria-hidden': 'true' }, [
      el('img', { src: avatar, alt: '', loading: 'lazy', decoding: 'async' }),
    ]);
  }

  function photo(item, alt, onOpen) {
    var img = el('img', { src: item.img, alt: alt, loading: 'lazy', decoding: 'async',
                          width: item.w, height: item.h });
    if (!onOpen) return el('span', { class: 'vs-photo' }, [img]);
    return el('button', { class: 'vs-photo', type: 'button', 'aria-label': 'Agrandir la tenue de ' + item.u,
                          onclick: function () { onOpen(item); } }, [img]);
  }

  var MONTHS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
                'août', 'septembre', 'octobre', 'novembre', 'décembre'];

  // A gallery label: the member, then the likes and the month
  function credit(item) {
    return el('span', { class: 'vs-credit' }, [
      el('strong', { text: '@' + item.u }),
      el('span', { class: 'vs-caption-meta',
                   text: plural(item.likes, 'like', 'likes') + (item.month ? ', en ' + MONTHS[item.month - 1] : '') }),
    ]);
  }

  function inView(node, callback, options) {
    if (!('IntersectionObserver' in window)) { callback(node); return; }
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { observer.unobserve(entry.target); callback(entry.target); }
      });
    }, options || { threshold: 0.35 });
    observer.observe(node);
  }

  // Light or dark: follow the page we are embedded in (Discourse theme, or the OS in the preview)
  function detectScheme(root) {
    var node = root.parentElement;
    while (node) {
      var bg = getComputedStyle(node).backgroundColor;
      var rgb = bg.match(/\d+(\.\d+)?/g);
      if (rgb && (rgb.length < 4 || Number(rgb[3]) > 0)) {
        var luminance = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
        return luminance < 0.5 ? 'dark' : 'light';
      }
      node = node.parentElement;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  // ---------------------------------------------------------------- lightbox

  function lightbox(root) {
    var img = el('img', { alt: '' });
    var who = el('span', { class: 'vs-credit' });
    var link = el('a', { target: '_blank', rel: 'noopener', text: 'Voir le post sur le forum' });
    var dialog = el('dialog', { class: 'vs-lightbox', 'aria-label': 'Tenue agrandie' }, [
      el('div', { class: 'vs-lightbox__inner' }, [
        img,
        el('div', { class: 'vs-lightbox__bar' }, [
          who, link,
          el('button', { class: 'vs-lightbox__close', type: 'button', text: 'Fermer',
                         onclick: function () { dialog.close(); } }),
        ]),
      ]),
    ]);
    dialog.addEventListener('click', function (event) { if (event.target === dialog) dialog.close(); });
    root.appendChild(dialog);
    return function open(item) {
      img.src = item.img;
      img.alt = 'Tenue de ' + item.u;
      who.replaceChildren(credit(item));
      link.href = item.url;
      if (dialog.showModal) dialog.showModal(); else window.open(item.url, '_blank', 'noopener');
    };
  }

  // -------------------------------------------------------------------- hero

  function hero(data) {
    var columns = [];
    for (var c = 0; c < 6; c++) columns.push([]);
    data.mosaic.forEach(function (src, i) { columns[i % 6].push(src); });

    var mosaic = el('div', { class: 'vs-hero__mosaic', 'aria-hidden': 'true' }, columns.map(function (srcs) {
      // each column is doubled so the drift loops without a seam
      var images = srcs.concat(srcs).map(function (src) {
        return el('img', { src: src, alt: '', loading: 'eager', decoding: 'async' });
      });
      return el('div', { class: 'vs-hero__column' }, images);
    }));

    var label = data.period.label;
    var counters = [
      ['tenues', data.stats.outfits],
      ['membres', data.stats.members],
      ['likes', data.stats.likes],
    ].map(function (pair) {
      return el('div', {}, [el('dt', { text: pair[0] }), el('dd', { 'data-count': pair[1], text: number.format(pair[1]) })]);
    });

    // A flannel sheet over the mosaic, with the period cut out of it
    var maskId = 'vs-cut-' + Math.random().toString(36).slice(2);
    var year = svg('text', { x: '50%', y: '43%', 'text-anchor': 'middle', 'dominant-baseline': 'central', fill: '#000' });
    year.textContent = label;
    var sheet = svg('svg', { class: 'vs-hero__sheet', 'aria-hidden': 'true', focusable: 'false' }, [
      svg('defs', {}, [svg('mask', { id: maskId }, [
        svg('rect', { width: '100%', height: '100%', fill: '#fff' }),
        year,
      ])]),
      svg('rect', { class: 'vs-hero__cloth', width: '100%', height: '100%', mask: 'url(#' + maskId + ')' }),
    ]);

    var header = el('header', { class: 'vs-hero vs-night' }, [
      mosaic,
      sheet,
      el('div', { class: 'vs-masthead' }, [
        el('span', { class: 'vs-masthead__name', text: 'Borasification' }),
        el('span', { text: 'Outfit of the day, ' + label }),
      ]),
      el('div', {}),
      el('div', { class: 'vs-hero__foot' }, [
        el('div', {}, [
          el('h1', { class: 'vs-hero__title', text: 'Le vestiaire OOTD' }),
          el('p', { class: 'vs-hero__lead',
                    text: data.period.intro + ', la communauté a posté ses tenues jour après jour. Voici ce qu\'on en retient.' }),
        ]),
        el('dl', { class: 'vs-care', 'aria-label': 'Les chiffres ' + data.period.of }, counters),
      ]),
    ]);

    // On a narrow screen the period stacks on two lines: 20 over 25, T1 over 2026
    function lines(narrow) {
      if (!narrow) return [label];
      if (label.indexOf(' ') > 0) return label.split(' ');
      return label.length === 4 ? [label.slice(0, 2), label.slice(2)] : [label];
    }

    header._setup = function () {
      function fit() {
        var w = header.clientWidth, h = header.clientHeight;
        var rows = lines(w < 640);
        var longest = Math.max.apply(null, rows.map(function (r) { return r.length; }));
        // as big as the screen allows, leaving room for the title below
        var size = Math.min(w * 1.45 / longest, h * (rows.length > 1 ? 0.27 : 0.62));
        year.setAttribute('font-size', size);
        year.replaceChildren.apply(year, rows.map(function (row, i) {
          var span = svg('tspan', { x: '50%', dy: i ? '0.86em' : (-(rows.length - 1) * 0.43) + 'em' });
          span.textContent = row;
          return span;
        }));
      }
      fit();
      window.addEventListener('resize', fit);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
    };
    return header;
  }

  // The one orchestrated entrance: the care label counts up when the page opens
  function countUp(root) {
    var cells = root.querySelectorAll('.vs-care dd');
    if (reduceMotion) return;
    var start = null;
    var duration = 1800;
    function frame(time) {
      if (start === null) start = time;
      var t = Math.min(1, (time - start) / duration);
      var eased = 1 - Math.pow(1 - t, 4);
      cells.forEach(function (cell) {
        cell.textContent = number.format(Math.round(Number(cell.dataset.count) * eased));
      });
      if (t < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  // ------------------------------------------------------------------ runway

  function runway(data, open) {
    var looks = data.top.filter(function (item) { return item.rank > 10; }).reverse();
    if (!looks.length) return null;
    var first = looks[0].rank;
    var last = looks[looks.length - 1].rank;

    var track = el('div', { class: 'vs-runway__track' }, looks.map(function (item) {
      return el('figure', { class: 'vs-look' }, [
        el('span', { class: 'vs-look__rank', 'aria-hidden': 'true', text: String(item.rank) }),
        photo(item, 'Tenue numéro ' + item.rank + ', de ' + item.u, open),
        el('figcaption', {}, [el('span', { class: 'vs-sr', text: 'Numéro ' + item.rank + '. ' }), credit(item)]),
      ]);
    }));

    var progress = el('span');
    var section = el('section', { class: 'vs-runway vs-night', 'aria-labelledby': 'vs-runway-title' }, [
      el('div', { class: 'vs-runway__stage' }, [
        el('div', { class: 'vs-runway__head' }, [
          el('h2', { class: 'vs-h2', id: 'vs-runway-title', text: 'Le défilé' }),
          el('p', { class: 'vs-lead', text: 'Du ' + first + 'e au ' + last + 'e : les tenues qui ont le plus plu '
                                             + data.period.of + ', avant le top 10.' }),
        ]),
        el('div', { class: 'vs-runway__viewport' }, [track]),
        el('div', { class: 'vs-runway__progress', 'aria-hidden': 'true' }, [progress]),
      ]),
    ]);

    section._setup = function () {
      if (reduceMotion) { section.classList.add('vs-runway--static'); return; }
      var figures = Array.prototype.slice.call(track.querySelectorAll('.vs-look'));
      var distance = 0;
      var centres = [];

      function measure() {
        distance = Math.max(0, track.scrollWidth - window.innerWidth);
        section.style.height = (window.innerHeight + distance) + 'px';
        centres = figures.map(function (f) { return f.offsetLeft + f.offsetWidth / 2; });
        update();
      }

      function update() {
        var top = section.getBoundingClientRect().top;
        var p = distance ? Math.min(1, Math.max(0, -top / distance)) : 0;
        var shift = -p * distance;
        var half = window.innerWidth / 2;
        track.style.transform = 'translate3d(' + shift + 'px, 0, 0)';
        figures.forEach(function (figure, i) {
          // -1 on the left edge, 0 in the centre, 1 on the right edge
          var d = Math.max(-1.5, Math.min(1.5, (centres[i] + shift - half) / half));
          var away = Math.min(1, Math.abs(d));
          // the number lines up with its photo in the centre and trails on each side
          figure.firstChild.style.transform = 'translate3d(' + (d * 90) + 'px, 0, 0)';
          figure.style.setProperty('--vs-spot-scale', (1 - away * 0.14).toFixed(3));
          figure.style.setProperty('--vs-spot-grey', (away * 0.9).toFixed(3));
        });
        section.style.setProperty('--vs-progress', p.toFixed(4));
      }

      var ticking = false;
      scroller.addEventListener('scroll', function () {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(function () { ticking = false; update(); });
      }, { passive: true });
      window.addEventListener('resize', measure);
      track.querySelectorAll('img').forEach(function (img) { img.addEventListener('load', measure, { once: true }); });
      measure();
    };
    return section;
  }

  // --------------------------------------------------------------- countdown

  function countItem(item, data, open) {
    var isFirst = item.rank === 1;
    return el('li', { class: 'vs-count' + (isFirst ? ' vs-count--first' : ''), 'data-rank': item.rank,
                      'data-user': item.u }, [
      isFirst ? el('h3', { class: 'vs-count__title', text: 'La tenue ' + data.period.of }) : null,
      el('span', { class: 'vs-count__num', 'aria-hidden': 'true', text: String(item.rank) }),
      photo(item, 'Tenue numéro ' + item.rank + ', de ' + item.u, open),
      el('div', { class: 'vs-count__caption' }, [
        el('span', { class: 'vs-count__likes', text: plural(item.likes, 'like', 'likes') }),
        el('span', { class: 'vs-credit' }, [
          el('strong', { text: '@' + item.u }),
          el('span', { class: 'vs-caption-meta', text: 'en ' + MONTHS[item.month - 1] }),
        ]),
      ]),
    ]);
  }

  // Ranks 10 to 2 as a magazine spread: a giant numeral holds the left page
  // and turns as the outfits pass on the right. Then number 1, alone.
  function countdown(data, open) {
    var ten = data.top.filter(function (item) { return item.rank <= 10; }).reverse();
    if (!ten.length) return null;
    var rest = ten.filter(function (item) { return item.rank > 1; });
    var first = ten.filter(function (item) { return item.rank === 1; })[0];

    var number = el('span', { class: 'vs-spread__number', 'aria-hidden': 'true',
                              text: rest.length ? String(rest[0].rank) : '' });
    var who = el('p', { class: 'vs-spread__who vs-lead', 'aria-hidden': 'true' });
    var spread = rest.length ? el('div', { class: 'vs-spread' }, [
      el('div', { class: 'vs-spread__dial' }, [number, who]),
      el('ol', { class: 'vs-countdown', reversed: true, start: rest[0].rank },
         rest.map(function (item) { return countItem(item, data, open); })),
    ]) : null;

    var section = el('section', { class: 'vs-section', 'aria-labelledby': 'vs-count-title' }, [
      el('div', { class: 'vs-section__head' }, [
        el('h2', { class: 'vs-h2', id: 'vs-count-title', text: 'Le top 10' }),
        el('p', { class: 'vs-lead', text: 'Classées par likes reçus pendant leurs trente premiers jours.' }),
      ]),
      spread,
      first ? el('ol', { class: 'vs-countdown vs-finale', start: 1 }, [countItem(first, data, open)]) : null,
    ]);

    section._setup = function () {
      if (!spread || !('IntersectionObserver' in window)) return;
      // the item crossing the middle of the screen sets the dial
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var rank = entry.target.getAttribute('data-rank');
          if (number.textContent === rank) return;
          number.textContent = rank;
          who.textContent = '@' + entry.target.getAttribute('data-user');
          number.classList.remove('is-turning');
          void number.offsetWidth;  // restart the turn animation
          number.classList.add('is-turning');
        });
      }, { rootMargin: '-45% 0px -45% 0px' });
      spread.querySelectorAll('.vs-count').forEach(function (item) { observer.observe(item); });
      who.textContent = '@' + rest[0].u;
    };
    return section;
  }

  // The members' names, rolling like the credits after a show
  function credits(data) {
    var names = data.members.slice().sort(function (a, b) { return b.likes - a.likes; })
                            .slice(0, 60).map(function (m) { return m.u; });
    if (names.length < 4) return null;
    function row() {
      var children = [];
      names.forEach(function (name) {
        children.push(el('span', { class: 'vs-credits__name', text: '@' + name }));
        children.push(el('span', { class: 'vs-credits__stitch', 'aria-hidden': 'true' }));
      });
      return children;
    }
    return el('div', { class: 'vs-credits', 'aria-label': 'Les membres ' + data.period.of }, [
      // doubled so the roll loops without a seam
      el('div', { class: 'vs-credits__row' }, row().concat(row())),
    ]);
  }

  function setupCountdown(root) {
    root.querySelectorAll('.vs-count').forEach(function (item) {
      inView(item, function () {
        item.classList.add('is-in');
        if (item.classList.contains('vs-count--first')) confetti(root);
      }, { threshold: 0.45 });
    });
  }

  // Fabric offcuts with pinked edges, for the outfit of the period only
  function confetti(root) {
    if (reduceMotion) return;
    var canvas = el('canvas', { class: 'vs-confetti', 'aria-hidden': 'true' });
    root.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    var ratio = window.devicePixelRatio || 1;
    var w = canvas.width = window.innerWidth * ratio;
    var h = canvas.height = window.innerHeight * ratio;
    var style = getComputedStyle(root);
    var colors = ['--vs-accent', '--vs-camel', '--vs-ink', '--vs-label'].map(function (v) {
      return style.getPropertyValue(v).trim();
    });
    var pieces = [];
    for (var i = 0; i < 150; i++) {
      pieces.push({
        x: w * (0.2 + Math.random() * 0.6), y: h * 0.45,
        vx: (Math.random() - 0.5) * 22 * ratio, vy: (-10 - Math.random() * 16) * ratio,
        size: (8 + Math.random() * 12) * ratio, turn: Math.random() * Math.PI, spin: (Math.random() - 0.5) * 0.3,
        color: colors[i % colors.length],
      });
    }
    var started = performance.now();
    function draw(time) {
      ctx.clearRect(0, 0, w, h);
      pieces.forEach(function (p) {
        p.vy += 0.55 * ratio; p.vx *= 0.985; p.vy *= 0.985;
        p.x += p.vx; p.y += p.vy; p.turn += p.spin;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.turn);
        ctx.scale(1, Math.abs(Math.cos(p.turn * 1.7)) * 0.8 + 0.2);
        ctx.fillStyle = p.color;
        // a rectangle of cloth whose short edges are cut with pinking shears
        var s = p.size, half = s / 2, teeth = 4, step = s / teeth;
        ctx.beginPath();
        ctx.moveTo(-half, -half * 0.6);
        for (var t = 0; t < teeth; t++) {
          ctx.lineTo(-half + step * (t + 0.5), -half * 0.6 - step * 0.35);
          ctx.lineTo(-half + step * (t + 1), -half * 0.6);
        }
        ctx.lineTo(half, half * 0.6);
        for (var b = teeth; b > 0; b--) {
          ctx.lineTo(-half + step * (b - 0.5), half * 0.6 + step * 0.35);
          ctx.lineTo(-half + step * (b - 1), half * 0.6);
        }
        ctx.closePath();
        ctx.fill();
        ctx.restore();
      });
      if (time - started < 4200) requestAnimationFrame(draw); else canvas.remove();
    }
    requestAnimationFrame(draw);
  }

  // ------------------------------------------------------------ tape measure

  function tape(data, open) {
    var months = data.monthly.filter(function (m) { return m.count > 0; });
    if (data.period.kind === 'month' || months.length < 2) return null;
    var max = Math.max.apply(null, months.map(function (m) { return m.count; }));
    var detail = el('div', { class: 'vs-tape-detail', 'aria-live': 'polite' });
    var buttons = [];

    function select(month, button) {
      buttons.forEach(function (b) { b.setAttribute('aria-pressed', b === button ? 'true' : 'false'); });
      var name = month.name.charAt(0).toUpperCase() + month.name.slice(1);
      var children = [];
      if (month.winner) children.push(photo(month.winner, 'Tenue du mois de ' + month.name + ', de ' + month.winner.u, open));
      children.push(el('div', {}, [
        el('p', { class: 'vs-tape-detail__month', text: name }),
        el('p', { text: plural(month.count, 'tenue postée', 'tenues postées') + '. La plus appréciée :' }),
        month.winner ? credit(month.winner) : null,
      ]));
      detail.replaceChildren.apply(detail, children);
    }

    var ribbon = el('div', { class: 'vs-tape', role: 'group', 'aria-label': 'Tenues par mois',
                             style: { '--vs-months': data.monthly.length } },
      data.monthly.map(function (month) {
        var button = el('button', {
          class: 'vs-tape__month', type: 'button', 'aria-pressed': 'false',
          'aria-label': month.name + ' : ' + plural(month.count, 'tenue', 'tenues'),
          style: { '--vs-share': (month.count / max).toFixed(3) },
          onclick: function () { select(month, button); },
        }, [
          el('span', { class: 'vs-tape__count', text: number.format(month.count) }),
          el('span', { class: 'vs-tape__bar' }),
          el('span', { class: 'vs-tape__ribbon', text: MONTH_ABBR[month.month - 1] }),
        ]);
        buttons.push(button);
        return button;
      }));

    var busiest = months.reduce(function (a, b) { return b.count > a.count ? b : a; });
    select(busiest, buttons[data.monthly.indexOf(busiest)]);

    return el('section', { class: 'vs-section vs-paper-ground', 'aria-labelledby': 'vs-tape-title' }, [
      el('div', { class: 'vs-section__head' }, [
        el('h2', { class: 'vs-h2', id: 'vs-tape-title', text: 'Au mètre ruban' }),
        el('p', { class: 'vs-lead', text: 'Mois par mois, combien de tenues ont été postées. Choisis un mois pour voir sa tenue la plus appréciée.' }),
      ]),
      ribbon,
      detail,
    ]);
  }

  // ----------------------------------------------------------------- buttons

  // Dense packing: each button takes the free spot nearest the centre,
  // biggest first, on an ellipse wider than tall so the pile fills the page
  function pack(circles, width, aspect) {
    var placed = [];
    circles.forEach(function (circle) {
      if (!placed.length) { circle.x = 0; circle.y = 0; placed.push(circle); return; }
      for (var ring = circle.r * 0.5; ; ring += 2) {
        var steps = Math.max(12, Math.round(ring / 3));
        var offset = Math.random() * Math.PI * 2;
        for (var k = 0; k < steps; k++) {
          var angle = offset + (k / steps) * Math.PI * 2;
          var x = Math.cos(angle) * ring * aspect, y = Math.sin(angle) * ring;
          var free = true;
          for (var j = 0; j < placed.length && free; j++) {
            var p = placed[j], dx = p.x - x, dy = p.y - y, gap = p.r + circle.r + 2;
            if (dx * dx + dy * dy < gap * gap) free = false;
          }
          if (free) { circle.x = x; circle.y = y; placed.push(circle); return; }
        }
      }
    });
    var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    placed.forEach(function (p) {
      minX = Math.min(minX, p.x - p.r); maxX = Math.max(maxX, p.x + p.r);
      minY = Math.min(minY, p.y - p.r); maxY = Math.max(maxY, p.y + p.r);
    });
    var scale = width / (maxX - minX);
    placed.forEach(function (p) { p.x = (p.x - minX) * scale; p.y = (p.y - minY) * scale; p.r *= scale; });
    return (maxY - minY) * scale;
  }

  function buttons(data, open) {
    var members = data.members.slice().sort(function (a, b) { return b.likes - a.likes; });
    if (members.length < 3) return null;
    var maxLikes = members[0].likes;
    var counts = members.map(function (m) { return m.count; }).sort(function (a, b) { return a - b; });
    var midCount = counts[Math.floor(counts.length * 0.75)];
    var panel = el('div', { class: 'vs-member-panel', 'aria-live': 'polite' }, [
      el('p', { class: 'vs-hint', text: 'Choisis un bouton pour voir les meilleures tenues de ce membre.' }),
    ]);
    var field = el('div', { class: 'vs-buttons', role: 'group', 'aria-label': 'Les membres' });
    var nodes = [];

    function show(member, node) {
      nodes.forEach(function (n) { n.setAttribute('aria-pressed', n === node ? 'true' : 'false'); });
      panel.replaceChildren.apply(panel, member.top.map(function (item) {
        return photo(item, 'Tenue de ' + member.u, open);
      }).concat([el('div', {}, [
        portrait(member.u, member.avatar, true),
        el('p', { class: 'vs-member-panel__name', text: '@' + member.u }),
        el('p', { class: 'vs-credit', text: plural(member.count, 'tenue', 'tenues') + ', '
                                            + plural(member.likes, 'like', 'likes')
                                            + (member.new ? '. Arrivé ' + data.period.this + '.' : '.') }),
      ])]));
    }

    function layout() {
      var width = field.clientWidth || 800;
      var circles = members.map(function (m) {
        return { m: m, r: Math.max(4, 60 * Math.sqrt(m.likes / maxLikes)) };
      });
      // wide screens get a wide pile; phones a rounder one
      var height = pack(circles, width, Math.max(1.1, Math.min(2.6, width / 500)));
      field.style.height = Math.ceil(height) + 'px';
      circles.forEach(function (c, i) {
        var node = nodes[i];
        node.style.left = c.x + 'px';
        node.style.top = c.y + 'px';
        node.style.width = node.style.height = (c.r * 2) + 'px';
        node.style.setProperty('--vs-r', (c.r * 2) + 'px');
      });
    }

    members.forEach(function (member) {
      var kind = member.new ? ' vs-button--new' : member.count >= midCount ? ' vs-button--mid' : '';
      var node = el('button', {
        class: 'vs-button' + kind + (member.avatar ? ' vs-button--face' : ''), type: 'button',
        'aria-pressed': 'false', title: '@' + member.u,
        'aria-label': '@' + member.u + ', ' + plural(member.likes, 'like', 'likes'),
        onclick: function () { show(member, node); },
      // profile pictures are small (~120 px): load them all at once, the pile appears whole
      }, member.avatar ? [el('img', { class: 'vs-button__face', src: member.avatar, alt: '',
                                      decoding: 'async' })] : []);
      nodes.push(node);
      field.appendChild(node);
    });

    var section = el('section', { class: 'vs-section', 'aria-labelledby': 'vs-buttons-title' }, [
      el('div', { class: 'vs-section__head' }, [
        el('h2', { class: 'vs-h2', id: 'vs-buttons-title', text: 'Bouton par bouton' }),
        el('p', { class: 'vs-lead', text: 'Chaque bouton est un membre. Plus il est grand, plus ses tenues ont reçu de likes ' + data.period.this + '.' }),
      ]),
      field,
      el('ul', { class: 'vs-buttons__legend' }, [
        el('li', {}, [el('span', { style: { '--vs-swatch': 'var(--vs-accent)' } }), 'Arrivé ' + data.period.this]),
        el('li', {}, [el('span', { style: { '--vs-swatch': 'var(--vs-camel)' } }), 'Parmi les plus réguliers']),
        el('li', {}, [el('span', { style: { '--vs-swatch': 'var(--vs-ink)' } }), 'Les autres membres']),
      ]),
      panel,
    ]);
    section._setup = function () { layout(); window.addEventListener('resize', layout); };
    return section;
  }

  // ------------------------------------------------------------ woven labels

  function labels(data, open) {
    var a = data.awards;
    var list = [
      ['member', 'Membre ' + data.period.of, 'La somme des likes de ses ' + data.period.best_n + ' meilleures tenues.'],
      ['pillar', 'Pilier de l\'OOTD', 'Le plus de tenues postées ' + data.period.this + '.'],
      ['rising', 'Révélation ' + data.period.of, 'Première tenue ' + data.period.this + ', et déjà remarquée.'],
      ['consistent', 'Le plus régulier', 'Le plus de tenues dans le meilleur quart de la période.'],
    ].filter(function (entry) { return a[entry[0]]; });
    if (!list.length) return null;

    var cards = list.map(function (entry, index) {
      var award = a[entry[0]];
      var photos = el('div', { class: 'vs-woven__photos' }, award.top.map(function (item) {
        return photo(item, 'Tenue de ' + award.u, open);
      }));
      var text = [
        el('h3', { class: 'vs-woven__award', text: entry[1] }),
        el('div', { class: 'vs-woven__who' }, [
          portrait(award.u, award.avatar),
          el('div', {}, [
            el('span', { class: 'vs-woven__name', text: '@' + award.u }),
            el('span', { class: 'vs-credit', text: award.detail }),
          ]),
        ]),
        el('p', { class: 'vs-credit', text: entry[2] }),
        award.podium.length ? el('ol', { class: 'vs-woven__podium', start: 2 }, award.podium.map(function (p, i) {
          return el('li', { text: (i + 2) + '. @' + p.u + ', ' + p.detail });
        })) : null,
      ];
      // the main label sets its text beside the photos; the others stack them
      var body = index === 0 ? [el('div', {}, text), photos] : text.slice(0, 2).concat([photos], text.slice(2));
      return el('article', { class: 'vs-woven' + (index === 0 ? ' vs-woven--main' : '') }, body);
    });

    return el('section', { class: 'vs-section vs-night', 'aria-labelledby': 'vs-labels-title' }, [
      el('div', { class: 'vs-section__head' }, [
        el('h2', { class: 'vs-h2', id: 'vs-labels-title', text: 'Cousus main' }),
        el('p', { class: 'vs-lead', text: 'Les membres qui ont marqué la période, chacun à sa façon.' }),
      ]),
      el('div', { class: 'vs-labels' }, cards),
    ]);
  }

  // --------------------------------------------------------------- your year

  function yours(data, options, open) {
    var names = Object.keys(data.wrapped).sort(function (a, b) { return a.localeCompare(b, 'fr'); });
    if (!names.length) return null;
    var body = el('div', { 'aria-live': 'polite' });

    function show(username) {
      var me = data.wrapped[username];
      if (!me) {
        body.replaceChildren(el('p', { class: 'vs-lead',
          text: 'Pas encore assez de tenues ' + data.period.this + ' pour ton bilan. Poste ta prochaine tenue dans l\'OOTD.' }));
        return;
      }
      var stats = [
        ['tenues postées', number.format(me.count)],
        ['likes reçus', number.format(me.likes)],
        ['au classement, sur ' + data.stats.members, '#' + me.rank],
      ];
      if (me.best_month) stats.push(['ton meilleur mois', me.best_month, true]);
      if (me.fan) stats.push(['ton plus grand fan, ' + plural(me.fan.likes, 'like', 'likes'), '@' + me.fan.fan, true]);
      body.replaceChildren(el('div', { class: 'vs-yours' }, [
        el('div', {}, [
          el('div', { class: 'vs-yours__who' }, [
            portrait(username, me.avatar),
            el('span', { class: 'vs-woven__name', text: '@' + username }),
          ]),
          el('dl', { class: 'vs-yours__stats' }, stats.map(function (s) {
            return el('div', {}, [el('dt', { text: s[0] }), el('dd', { class: s[2] ? 'vs-dd--word' : null, text: s[1] })]);
          })),
          me.honours.length ? el('ul', { class: 'vs-yours__honours', 'aria-label': 'Tes distinctions' },
                                 me.honours.map(function (h) { return el('li', { text: h }); })) : null,
        ]),
        el('div', { class: 'vs-yours__photos' }, me.top.map(function (item) {
          return photo(item, 'Ta tenue', open);
        })),
      ]));
    }

    var head = el('div', { class: 'vs-section__head' }, [
      el('h2', { class: 'vs-h2', id: 'vs-yours-title', text: 'Ton bilan' }),
      el('p', { class: 'vs-lead', text: 'Tes chiffres ' + data.period.of + ', tes meilleures tenues et tes distinctions.' }),
    ]);
    var children = [head];
    var current = options.currentUser && options.currentUser.username;

    if (options.preview || !current) {
      // Preview only: on the forum, the logged-in member sees their own year
      var select = el('select', { onchange: function () { show(select.value); } }, names.map(function (n) {
        return el('option', { value: n, text: '@' + n });
      }));
      children.push(el('label', { class: 'vs-yours__pick' }, ['Aperçu : voir le bilan de', select]));
      var first = data.awards.member && data.wrapped[data.awards.member.u] ? data.awards.member.u : names[0];
      select.value = first;
      show(first);
    } else {
      var match = names.filter(function (n) { return n.toLowerCase() === current.toLowerCase(); })[0];
      show(match || current);
    }
    children.push(el('div', { class: 'vs-tag-wrap' }, [el('div', { class: 'vs-tag' }, [body])]));
    return el('section', { class: 'vs-section', 'aria-labelledby': 'vs-yours-title' }, children);
  }

  // ------------------------------------------------------------------ render

  function render(root, data, options) {
    options = options || {};
    scroller = options.scroller || window;
    root.classList.add('ootd-story', 'vs-js');
    root.setAttribute('data-scheme', options.scheme || detectScheme(root));
    root.replaceChildren();
    var open = lightbox(root);

    var sections = [
      hero(data),
      credits(data),
      runway(data, open),
      countdown(data, open),
      tape(data, open),
      buttons(data, open),
      labels(data, open),
      yours(data, options, open),
      el('footer', { class: 'vs-footer vs-night' }, [
        el('p', {}, ['Merci pour toutes ces tenues. On se retrouve dans ',
                     el('a', { href: data.ootd_url, text: 'l\'OOTD' }), '.']),
      ]),
    ].filter(Boolean);
    sections.forEach(function (section) { root.appendChild(section); });
    sections.forEach(function (section) { if (section._setup) section._setup(); });
    countUp(root);
    setupCountdown(root);
  }

  window.OotdStory = { render: render };
})();
