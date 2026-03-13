/**
 * Tiny Canvas-based sparkline renderer.
 * Draws a 12-point line chart inline.
 */

function drawSparkline(canvas, data, options = {}) {
  const {
    color = '#dde44c',
    fillColor = 'rgba(221,228,76,0.1)',
    lineWidth = 1.5,
    highlightLast = true,
  } = options;

  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;

  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.scale(dpr, dpr);

  if (!data || data.length < 2) return;

  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;

  const stepX = w / (data.length - 1);
  const padY = 3;

  function getY(val) {
    return h - padY - ((val - min) / range) * (h - padY * 2);
  }

  // Fill
  ctx.beginPath();
  ctx.moveTo(0, getY(data[0]));
  for (let i = 1; i < data.length; i++) {
    ctx.lineTo(i * stepX, getY(data[i]));
  }
  ctx.lineTo((data.length - 1) * stepX, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  ctx.fillStyle = fillColor;
  ctx.fill();

  // Line
  ctx.beginPath();
  ctx.moveTo(0, getY(data[0]));
  for (let i = 1; i < data.length; i++) {
    ctx.lineTo(i * stepX, getY(data[i]));
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.stroke();

  // Highlight last point
  if (highlightLast) {
    const lastX = (data.length - 1) * stepX;
    const lastY = getY(data[data.length - 1]);
    ctx.beginPath();
    ctx.arc(lastX, lastY, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  }
}

// Render all sparklines in the DOM
function renderAllSparklines() {
  document.querySelectorAll('.sparkline-canvas').forEach(canvas => {
    const data = JSON.parse(canvas.dataset.values || '[]');
    const spike = canvas.dataset.spike === 'true';
    drawSparkline(canvas, data, {
      color: spike ? '#ff7c53' : '#dde44c',
      fillColor: spike ? 'rgba(255,124,83,0.1)' : 'rgba(221,228,76,0.1)',
    });
  });
}
