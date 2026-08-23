(() => {
  "use strict";

  const root = document.documentElement;

  const readGain = () =>
    parseFloat(getComputedStyle(root).getPropertyValue("--motion-gain")) || 0;

  const naturalGain = (() => {
    const q = new URLSearchParams(location.search).get("motion");
    if (q === "off") return 0;
    if (q === "full") return 1;
    return matchMedia("(prefers-reduced-motion: reduce)").matches ? 0.25 : 1;
  })();

  let currentGain = readGain();

  // ---------- reveal on scroll ----------
  const revealItems = document.querySelectorAll(".reveal");

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("in-view");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -60px 0px" }
    );
    revealItems.forEach((el) => observer.observe(el));
  } else {
    revealItems.forEach((el) => el.classList.add("in-view"));
  }

  // red de seguridad: un observer mudo (pestaña en segundo plano, panel sin
  // dimensionar) no debe dejar contenido invisible para siempre
  window.addEventListener("load", () => {
    setTimeout(() => {
      document.querySelectorAll(".reveal:not(.in-view)").forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.top < window.innerHeight && rect.bottom > 0) {
          el.classList.add("in-view");
        }
      });
    }, 400);
  });

  // ---------- paso activo de "cómo funciona" ----------
  const stepEls = document.querySelectorAll(".step[data-step]");
  const counterNum = document.querySelector(".funciona-counter [data-count]");

  if (stepEls.length && "IntersectionObserver" in window) {
    const stepObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          entry.target.classList.toggle("active", entry.isIntersecting);
          if (entry.isIntersecting && counterNum) {
            counterNum.textContent = entry.target.dataset.step.padStart(2, "0");
          }
        });
      },
      { rootMargin: "-45% 0px -45% 0px", threshold: 0 }
    );
    stepEls.forEach((el) => stepObserver.observe(el));
  }

  // ---------- micro-interacciones de puntero (imán) ----------
  const attachMagnetic = (el, strength) => {
    el.addEventListener("mousemove", (event) => {
      const rect = el.getBoundingClientRect();
      const relX = event.clientX - (rect.left + rect.width / 2);
      const relY = event.clientY - (rect.top + rect.height / 2);
      const mx = (relX / (rect.width / 2)) * strength;
      const my = (relY / (rect.height / 2)) * strength;
      el.style.translate = `${mx.toFixed(1)}px ${my.toFixed(1)}px`;
    });
    el.addEventListener("mouseleave", () => {
      el.style.translate = "0px 0px";
    });
  };

  document.querySelectorAll(".cta, .ghost").forEach((el) => attachMagnetic(el, 8));
  document.querySelectorAll(".chip").forEach((el) => attachMagnetic(el, 5));

  // ---------- parallax en capas + salida del hero (escalado por --motion-gain) ----------
  const layers = document.querySelectorAll("[data-speed]");
  const heroSection = document.querySelector(".hero");
  const heroInner = document.querySelector(".hero-inner");
  let ticking = false;

  const updateOnScroll = () => {
    const y = window.scrollY;

    layers.forEach((el) => {
      const speed = parseFloat(el.dataset.speed) * currentGain;
      el.style.translate = `0px ${(y * speed).toFixed(1)}px`;
    });

    if (heroSection && heroInner) {
      const heroHeight = heroSection.offsetHeight || window.innerHeight;
      const progress = Math.min(1, Math.max(0, y / heroHeight));
      // la opacidad NUNCA se escala por el dial (regla de la casa); el
      // recorrido (traslado + escala) sí, y a gain 0 se queda quieto.
      heroInner.style.opacity = String(1 - progress * 0.7);
      heroInner.style.translate = `0px ${(-progress * 40 * currentGain).toFixed(1)}px`;
      heroInner.style.scale = String(1 - progress * 0.06 * currentGain);
    }

    ticking = false;
  };

  const onScroll = () => {
    if (!ticking) {
      window.requestAnimationFrame(updateOnScroll);
      ticking = true;
    }
  };

  window.addEventListener("scroll", onScroll, { passive: true });
  updateOnScroll();

  // ---------- válvula de movimiento (footer) ----------
  const motionToggle = document.getElementById("motionToggle");

  if (motionToggle) {
    const syncLabel = () => {
      const off = currentGain === 0;
      motionToggle.setAttribute("aria-pressed", String(off));
      motionToggle.textContent = off ? "Activar movimiento" : "Reducir movimiento";
    };

    syncLabel();

    motionToggle.addEventListener("click", () => {
      if (currentGain === 0) {
        try {
          localStorage.removeItem("vidorq-motion");
        } catch (e) {
          /* almacenamiento no disponible: el toggle sigue funcionando en esta visita */
        }
        currentGain = naturalGain;
      } else {
        try {
          localStorage.setItem("vidorq-motion", "off");
        } catch (e) {
          /* almacenamiento no disponible: el toggle sigue funcionando en esta visita */
        }
        currentGain = 0;
      }
      root.style.setProperty("--motion-gain", String(currentGain));
      root.classList.toggle("motion", currentGain > 0);
      syncLabel();
      updateOnScroll();
    });
  }
})();
