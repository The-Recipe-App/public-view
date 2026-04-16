import React, { useEffect, useRef } from "react";

/*
  ProcessingLoginCanvas - "The Clerk"

  A lone clerk at a terminal, typing your details into the system.
  Old-school feel. Transparent background. Cheap to render.

  Story beats (looping):
    1. Clerk types rapidly - keys animate, screen fills line by line
    2. Every ~18 keystrokes clerk hits ENTER - glowing packet
       travels along a wire to the server on the right
    3. Server LEDs blink orange in acknowledgement
    4. Clerk leans back a beat, then resumes

  Rendering budget:
    - Only fillRect, arc, bezierCurveTo - no shadow blur, no per-frame gradients
    - Transparent canvas (clearRect only)
    - Runs at 60 fps on decade-old hardware
*/

const TAU = Math.PI * 2;

export default function ProcessingLoginCanvas({ height = 260 }) {
  const canvasRef = useRef(null);
  const rafRef    = useRef(0);
  const stateRef  = useRef(null);

  /* init mutable scene state once */
  if (!stateRef.current) {
    stateRef.current = {
      t:            0,
      lines:        Array.from({ length: 6 }, () => 12 + Math.random() * 58),
      cursorOn:     true,
      lastBeat:     -1,
      packets:      [],
      serverAck:    0,
      leanBack:     0,
      keyCount:     0,
    };
  }

  /* HiDPI resize */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width  = rect.width  * dpr;
      canvas.height = rect.height * dpr;
      canvas.getContext("2d").scale(dpr, dpr);
    };
    canvas.style.width  = "100%";
    canvas.style.height = `${height}px`;
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [height]);

  /* animation loop */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const s   = stateRef.current;

    function loop() {
      rafRef.current = requestAnimationFrame(loop);
      s.t += 0.016;
      const t = s.t;

      const W = canvas.width  / dpr;
      const H = canvas.height / dpr;

      ctx.clearRect(0, 0, W, H);

      /* layout */
      const deskY  = H * 0.74;
      const clerkX = W * 0.36;
      const monX   = W * 0.36;
      const monTopY= deskY - 116;
      const kbX    = W * 0.43;
      const kbY    = deskY - 6;
      const srvX   = W * 0.80;
      const srvY   = deskY - 84;

      /* wire endpoints */
      const wireX1 = kbX + 20;
      const wireY1 = kbY + 4;
      const wireX2 = srvX - 22;
      const wireY2 = srvY + 42;

      /* ── state update ── */
      const isLeaning = s.leanBack > 0;
      s.leanBack      = Math.max(0, s.leanBack - 0.016);
      s.serverAck     = Math.max(0, s.serverAck - 0.016);

      /* typing beat */
      const beat     = Math.floor(t * 9);
      const newBeat  = beat !== s.lastBeat;
      s.lastBeat     = beat;

      if (newBeat && !isLeaning) {
        s.keyCount++;

        /* grow current line */
        if (s.lines.length === 0) s.lines.push(0);
        s.lines[s.lines.length - 1] += 4 + Math.random() * 7;

        /* wrap line */
        if (s.lines[s.lines.length - 1] > 84) {
          s.lines.push(0);
          if (s.lines.length > 9) s.lines.shift();
        }

        /* ENTER every ~20 keys */
        if (s.keyCount >= 20) {
          s.keyCount  = 0;
          s.leanBack  = 1.3;
          s.packets.push({ prog: 0, speed: 0.024 + Math.random() * 0.01, acked: false });
          s.lines.push(0);
          if (s.lines.length > 9) s.lines.shift();
        }
      }

      /* advance packets */
      for (const pk of s.packets) {
        pk.prog += pk.speed;
        if (pk.prog >= 1 && !pk.acked) {
          pk.acked   = true;
          s.serverAck = 0.8;
        }
      }
      s.packets = s.packets.filter(pk => pk.prog < 1.06);

      s.cursorOn = Math.floor(t * 1.7) % 2 === 0;

      /* ── draw ── */
      drawDesk(ctx, W, deskY);
      drawMonitor(ctx, monX, monTopY, s);
      drawClerk(ctx, clerkX, deskY, t, s, isLeaning);
      drawKeyboard(ctx, kbX, kbY, t, isLeaning);
      drawWire(ctx, wireX1, wireY1, wireX2, wireY2, s.packets);
      drawServer(ctx, srvX, srvY, t, s.serverAck);
    }

    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  return (
    <div className="w-full flex items-center justify-center py-2" aria-hidden>
      <canvas ref={canvasRef} style={{ height, display: "block" }} />
    </div>
  );
}

/* ━━━━ DESK ━━━━ */
function drawDesk(ctx, W, y) {
  ctx.fillStyle = "rgba(0,0,0)";
  ctx.fillRect(0, y, W, 2);
  ctx.fillStyle = "rgba(255,255,255,0.1)";
  ctx.fillRect(0, y + 2, W, 36);
}

/* ━━━━ MONITOR ━━━━ */
function drawMonitor(ctx, cx, topY, s) {
  const mW = 110, mH = 74;
  const mx = cx - mW / 2;

  /* chassis */
  ctx.fillStyle = "rgba(255,255,255,0.07)";
  rr(ctx, mx, topY, mW, mH, 5); ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.11)";
  ctx.lineWidth = 1; ctx.stroke();

  /* screen */
  ctx.fillStyle = "rgba(4,18,8,0.92)";
  rr(ctx, mx + 4, topY + 4, mW - 8, mH - 8, 2); ctx.fill();

  /* phosphor scan-line shimmer - single cheap rect */
  const scanLine = ((s.t * 30) % (mH - 10));
  ctx.fillStyle = "rgba(80,220,100,0.04)";
  ctx.fillRect(mx + 4, topY + 4 + scanLine, mW - 8, 4);

  /* text lines */
  const lineH = 7;
  for (let i = 0; i < s.lines.length; i++) {
    const lw    = Math.min(s.lines[i], mW - 18);
    const isLast = i === s.lines.length - 1;
    const age   = s.lines.length - 1 - i;
    const alpha = Math.max(0.12, 0.75 - age * 0.09);
    ctx.fillStyle = `rgba(80,220,100,${alpha})`;
    ctx.fillRect(mx + 7, topY + 6 + i * lineH, lw, 3);

    /* cursor */
    if (isLast && s.cursorOn) {
      ctx.fillStyle = "rgba(80,220,100,0.95)";
      ctx.fillRect(mx + 7 + lw + 2, topY + 5 + i * lineH, 4, 5);
    }
  }

  /* stand */
  ctx.fillStyle = "rgba(255,255,255,0.05)";
  ctx.fillRect(cx - 3, topY + mH, 6, 10);
  ctx.fillRect(cx - 15, topY + mH + 9, 30, 3);
}

/* ━━━━ KEYBOARD ━━━━ */
function drawKeyboard(ctx, cx, y, t, isLeaning) {
  const kW = 92, kH = 13;
  ctx.fillStyle = "rgba(3,3,3)";
  rr(ctx, cx - kW / 2, y, kW, kH, 2); ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.09)";
  ctx.lineWidth = 0.5; ctx.stroke();

  /* key rows - subtle lines */
  for (let row = 0; row < 2; row++) {
    ctx.fillStyle = "rgba(0,0,0,0.18)";
    ctx.fillRect(cx - kW / 2 + 4, y + 2 + row * 5, kW - 8, 3);
  }

  /* animated key press */
  if (!isLeaning) {
    const beat = t * 9;
    const kx   = cx - 28 + (Math.sin(beat * 0.7) * 0.5 + 0.5) * 54;
    ctx.fillStyle = "rgba(249,115,22,0.6)";
    rr(ctx, kx - 5, y + 1, 10, kH - 2, 1); ctx.fill();
  }
}

/* ━━━━ WIRE + PACKETS ━━━━ */
function drawWire(ctx, x1, y1, x2, y2, packets) {
  const cp1x = x1 + (x2 - x1) * 0.3;
  const cp1y = y1 + 32;
  const cp2x = x1 + (x2 - x1) * 0.7;
  const cp2y = y2 + 32;

  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, x2, y2);
  ctx.strokeStyle = "rgba(0,0,0)";
  ctx.lineWidth = 2.5;
  ctx.stroke();

  for (const pk of packets) {
    const p  = bezierPt(pk.prog, x1, y1, cp1x, cp1y, cp2x, cp2y, x2, y2);
    const a  = Math.sin(Math.min(pk.prog, 1) * Math.PI);

    /* soft halo */
    ctx.beginPath();
    ctx.arc(p.x, p.y, 7, 0, TAU);
    ctx.fillStyle = `rgba(249,115,22,${0.1 * a})`;
    ctx.fill();

    /* bright core */
    ctx.beginPath();
    ctx.arc(p.x, p.y, 2.5, 0, TAU);
    ctx.fillStyle = `rgba(249,115,22,${0.95 * a})`;
    ctx.fill();
  }
}

/* ━━━━ SERVER ━━━━ */
function drawServer(ctx, x, y, t, ack) {
  const sW = 40, sH = 76;
  const sx  = x - sW / 2;

  ctx.fillStyle = "rgba(0,0,0)";
  rr(ctx, sx, y, sW, sH, 3); ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.3)";
  ctx.lineWidth = 1; ctx.stroke();

  for (let i = 0; i < 5; i++) {
    const uy = y + 5 + i * 13;
    ctx.fillStyle = "rgba(255,255,255,0.08)";
    rr(ctx, sx + 3, uy, sW - 6, 9, 2); ctx.fill();

    /* LED */
    const on      = Math.sin(t * 3.2 + i * 1.9) > 0.25;
    const acking  = ack > 0 && i <= 2;
    const alpha   = acking ? (0.6 + ack * 0.4) : (on ? 0.85 : 0.15);
    const r = acking ? 249 : 80, g = acking ? 115 : 220, b = acking ? 22 : 100;

    ctx.beginPath();
    ctx.arc(sx + sW - 9, uy + 4.5, 2.5, 0, TAU);
    ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
    ctx.fill();
  }

  /* small ventilation slits */
  for (let v = 0; v < 4; v++) {
    ctx.fillStyle = "rgba(0,0,0,0.22)";
    ctx.fillRect(sx + 5, y + sH - 10 + v * 2, sW - 16, 1);
  }
}

/* ━━━━ CLERK ━━━━ */
function drawClerk(ctx, cx, baseY, t, s, isLeaning) {
  ctx.save();
  ctx.translate(cx, baseY);

  const breathe  = Math.sin(t * 1.5) * 1.5;
  /* lean eases in/out smoothly */
  const leanProg = isLeaning ? Math.sin((1.3 - s.leanBack) / 1.3 * Math.PI) : 0;
  const lean     = leanProg * 9;
  const blink    = Math.sin(t * 0.85) > 0.93 ? 0.1 : 1;



  /* ── torso ── */
  ctx.fillStyle = "rgba(68,114,196)";
  rr(ctx, -16 + lean * 0.3, -50 + breathe, 42, 52, 9); ctx.fill();

  /* shirt highlight stripe */
  ctx.fillStyle = "rgba(68,114,196)";
  rr(ctx, -8 + lean * 0.3, -50 + breathe, 10, 52, 5); ctx.fill();


  /* ── neck ── */
  ctx.fillStyle = "rgba(254,176,98, 0.6)";
  rr(ctx, 4 + lean * 0.5, -62 + breathe, 8, 14, 2); ctx.fill();

  /* ── head ── */
  const hx = 6 + lean * 0.7;
  const hy = -76 + breathe * 0.4;

  /* head shape */
  ctx.fillStyle = "rgba(254,176,98, 0.6)";
  ctx.beginPath();
  ctx.ellipse(hx, hy, 13, 15, 0.06, 0, TAU);
  ctx.fill();


  /* eyebrow */
  ctx.beginPath();
  ctx.moveTo(hx + 9 , hy - 5.6);
  ctx.lineTo(hx + 2, hy - 6);
  ctx.strokeStyle = "rgba(0,0,0)";
  ctx.lineWidth = 1.5;
  ctx.lineCap = "round";
  ctx.stroke();

  /* eye white */
  ctx.fillStyle = "rgba(255,255,255,0.55)";
  ctx.beginPath();
  ctx.ellipse(hx + 5, hy - 1, 3.5, 3.5 * blink, 0, 0, TAU);
  ctx.fill();

  /* pupil - glances at screen */
  if (blink > 0.3) {
    const gazeX = isLeaning ? 0 : -1.5; /* looking at screen */
    ctx.fillStyle = "rgba(30,30,40,0.85)";
    ctx.beginPath();
    ctx.arc(hx + 5 + gazeX, hy - 1, 1.8, 0, TAU);
    ctx.fill();
  }

  /* eyebrow */
  ctx.beginPath();
  ctx.moveTo(hx - 9, hy - 6);
  ctx.lineTo(hx - 2, hy - 5.6);
  ctx.strokeStyle = "rgba(0,0,0)";
  ctx.lineWidth = 1.5;
  ctx.lineCap = "round";
  ctx.stroke();

  /* eye white */
  ctx.fillStyle = "rgba(255,255,255,0.55)";
  ctx.beginPath();
  ctx.ellipse(hx - 5, hy - 1, 3.5, 3.5 * blink, 0, 0, TAU);
  ctx.fill();

  /* pupil - glances at screen */
  if (blink > 0.3) {
    const gazeX = isLeaning ? 0 : -1.5; /* looking at screen */
    ctx.fillStyle = "rgba(30,30,40,0.85)";
    ctx.beginPath();
    ctx.arc(hx - 5 + gazeX, hy - 1, 1.8, 0, TAU);
    ctx.fill();
  }


  /* ── arms ── */
  if (!isLeaning) {
    const lY = Math.sin(t * 10.5) * 6;
    const rY = Math.sin(t * 10.5 + Math.PI) * 6;
    drawArm(ctx, -12 + lean * 0.2, -34 + breathe, -8,  lY, "left");
    drawArm(ctx,  22 + lean * 0.2, -32 + breathe,  20, rY, "right");
  } else {
    /* resting after ENTER */
    drawArm(ctx, -12 + lean * 0.2, -34 + breathe, -6, -4 + lean * 0.3, "left");
    drawArm(ctx,  22 + lean * 0.2, -32 + breathe,  18, -3 + lean * 0.3, "right");
  }

  ctx.restore();
}

function drawArm(ctx, sx, sy, ex, ey, side) {
  const mx = (sx + ex) / 2 + (side === "left" ? -9 : 9);
  const my = (sy + ey) / 2 + 9;

  ctx.save();
  ctx.lineCap = "round";

  /* upper arm */
  ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(mx, my);
  ctx.strokeStyle = "rgba(254,176,98, 0.6)";
  ctx.lineWidth = 9; ctx.stroke();

  /* forearm */
  ctx.beginPath(); ctx.moveTo(mx, my); ctx.lineTo(ex, ey);
  ctx.strokeStyle = "rgba(254,176,98, 0.6)";
  ctx.lineWidth = 8; ctx.stroke();

  /* hand */
  ctx.beginPath(); ctx.arc(ex, ey, 4.5, 0, TAU);
  ctx.fillStyle = "rgba(254,176,98, 0.6)"; ctx.fill();

  ctx.restore();
}

/* ━━━━ HELPERS ━━━━ */
function bezierPt(prog, x1, y1, cp1x, cp1y, cp2x, cp2y, x2, y2) {
  const t  = Math.min(prog, 1);
  const mt = 1 - t;
  return {
    x: mt*mt*mt*x1 + 3*mt*mt*t*cp1x + 3*mt*t*t*cp2x + t*t*t*x2,
    y: mt*mt*mt*y1 + 3*mt*mt*t*cp1y + 3*mt*t*t*cp2y + t*t*t*y2,
  };
}

function rr(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y,     x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x,     y + h, r);
  ctx.arcTo(x,     y + h, x,     y,     r);
  ctx.arcTo(x,     y,     x + w, y,     r);
  ctx.closePath();
}