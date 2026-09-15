/* === Particle Network Background === */
(function() {
  const canvas = document.getElementById('particles');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let width, height;
  const particles = [];
  const PARTICLE_COUNT = 30;
  const CONNECTION_DIST = 130;
  const MOUSE_DIST = 160;

  let mouse = { x: -1000, y: -1000 };

  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', () => {
    resize();
    // 重置所有粒子位置，避免窗口变大后集中在左上角
    for (const p of particles) {
      p.x = Math.min(p.x, width);
      p.y = Math.min(p.y, height);
    }
  });

  let mouseThrottle = 0;
  window.addEventListener('mousemove', e => {
    const now = Date.now();
    if (now - mouseThrottle < 50) return; // 每 50ms 最多更新一次
    mouseThrottle = now;
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  });

  class Particle {
    constructor() {
      this.reset();
      this.y = Math.random() * height;
    }
    reset() {
      this.x = Math.random() * width;
      this.y = -10;
      this.vx = (Math.random() - 0.5) * 0.6;
      this.vy = Math.random() * 0.4 + 0.1;
      this.radius = Math.random() * 1.8 + 0.6;
      this.opacity = Math.random() * 0.6 + 0.2;
    }
    update() {
      this.x += this.vx;
      this.y += this.vy;
      if (this.y > height + 10) this.reset();
      if (this.x < -10) this.x = width + 10;
      if (this.x > width + 10) this.x = -10;
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(124, 130, 237, ${this.opacity})`;
      ctx.fill();
    }
  }

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const p = new Particle();
    p.y = Math.random() * height;
    particles.push(p);
  }

  function connect(p1, p2, dist) {
    const alpha = 1 - dist / CONNECTION_DIST;
    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.strokeStyle = `rgba(59, 130, 246, ${alpha * 0.2})`;
    ctx.lineWidth = 0.5;
    ctx.stroke();
  }

  function animate() {
    ctx.clearRect(0, 0, width, height);

    for (const p of particles) {
      p.update();
      p.draw();
    }

    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < CONNECTION_DIST) {
          connect(particles[i], particles[j], dist);
        }
      }

      // Mouse interaction
      const dx = mouse.x - particles[i].x;
      const dy = mouse.y - particles[i].y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < MOUSE_DIST) {
        ctx.beginPath();
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(mouse.x, mouse.y);
        ctx.strokeStyle = `rgba(124, 58, 237, ${(1 - dist / MOUSE_DIST) * 0.35})`;
        ctx.lineWidth = 0.7;
        ctx.stroke();
      }
    }

    requestAnimationFrame(animate);
  }

  animate();
})();

/* === Example question click → navigate to /app with question === */
document.querySelectorAll('.example-card').forEach(card => {
  card.addEventListener('click', () => {
    const question = card.dataset.question;
    if (question) {
      sessionStorage.setItem('initial_question', question);
    }
    window.location.href = '/app';
  });
});
