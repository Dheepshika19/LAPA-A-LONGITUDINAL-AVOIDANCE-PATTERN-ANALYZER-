/**
 * LAPA Animations
 * Handles all page transitions and interactive animations
 */

// Page transition animations are handled by showPage() in app.js using GSAP

/**
 * Animate indicator cards with values
 */
function animateIndicatorCard(cardId, targetValue) {
  const card = document.getElementById(cardId);
  if (!card) return;
  
  const valueElement = card.querySelector('.indicator-value');
  const duration = 1.5;
  
  gsap.to(
    { value: 0 },
    {
      value: targetValue,
      duration: duration,
      ease: 'power2.out',
      onUpdate: function() {
        valueElement.textContent = this.targets()[0].value.toFixed(2);
      }
    }
  );
}

/**
 * Morph button to success state
 */
function morphButtonSuccess(buttonId) {
  const btn = document.getElementById(buttonId);
  if (!btn) return;
  
  const originalText = btn.textContent;
  btn.textContent = '✓ Success!';
  btn.style.background = 'linear-gradient(135deg, #2a6a2a, #1a8a5a)';
  
  gsap.fromTo(btn,
    { scale: 1 },
    { 
      scale: 1.05, 
      duration: 0.3, 
      ease: 'back.out',
      yoyo: true,
      repeat: 1
    }
  );
  
  setTimeout(() => {
    btn.textContent = originalText;
    btn.style.background = 'linear-gradient(135deg, #2a9d8f, #1a6b8a)';
  }, 2000);
}

/**
 * Shake effect for errors
 */
function shakeElement(elementId) {
  const element = document.getElementById(elementId);
  if (!element) return;
  
  gsap.to(element, {
    x: -10,
    duration: 0.1,
    repeat: 5,
    yoyo: true,
    ease: 'power1.inOut',
    onComplete: () => {
      gsap.set(element, { x: 0 });
    }
  });
}

/**
 * Pulse effect for alerts
 */
function pulseElement(elementId) {
  const element = document.getElementById(elementId);
  if (!element) return;
  
  gsap.to(element, {
    scale: 1.05,
    duration: 0.3,
    repeat: 2,
    yoyo: true,
    ease: 'power2.inOut'
  });
}

/**
 * Fade in and slide up for list items
 */
function animateListItems(container, delay = 0.1) {
  const items = container.querySelectorAll('.entry-item, .stat-card');
  
  gsap.fromTo(items,
    { opacity: 0, y: 20 },
    {
      opacity: 1,
      y: 0,
      duration: 0.5,
      stagger: delay,
      ease: 'power2.out'
    }
  );
}

/**
 * Chart animation - bar chart
 */
function animateBarChart(bars, delay = 0.05) {
  gsap.fromTo(bars,
    { height: 0, opacity: 0 },
    {
      height: (i) => {
        return bars[i].getAttribute('data-height') || '100%';
      },
      opacity: 1,
      duration: 0.8,
      stagger: delay,
      ease: 'back.out'
    }
  );
}

/**
 * Chart animation - line/area chart draw
 */
function animateChartLine(path) {
  const length = path.getTotalLength();
  
  gsap.fromTo(path,
    {
      strokeDasharray: length,
      strokeDashoffset: length,
      opacity: 0
    },
    {
      strokeDashoffset: 0,
      opacity: 1,
      duration: 2,
      ease: 'power2.inOut'
    }
  );
}

/**
 * Number counter animation
 */
function animateCounter(elementId, targetValue, duration = 1) {
  const element = document.getElementById(elementId);
  if (!element) return;
  
  gsap.to(
    { value: parseInt(element.textContent) || 0 },
    {
      value: targetValue,
      duration: duration,
      ease: 'power2.out',
      onUpdate: function() {
        element.textContent = Math.round(this.targets()[0].value);
      }
    }
  );
}

/**
 * Progress ring animation
 */
function animateProgressRing(circle, percent, duration = 1.5) {
  const circumference = 2 * Math.PI * circle.r.baseVal.value;
  
  gsap.fromTo(circle,
    { 
      strokeDashoffset: circumference
    },
    {
      strokeDashoffset: circumference - (percent / 100) * circumference,
      duration: duration,
      ease: 'power2.inOut'
    }
  );
}

/**
 * Floating animation (for background elements)
 */
function startFloatingAnimation(elementId) {
  const element = document.getElementById(elementId);
  if (!element) return;
  
  gsap.to(element, {
    y: -20,
    duration: 3,
    repeat: -1,
    yoyo: true,
    ease: 'sine.inOut'
  });
}

/**
 * Scale animation for card interactions
 */
function scaleOnHover(elementId) {
  const element = document.getElementById(elementId);
  if (!element) return;
  
  element.addEventListener('mouseenter', () => {
    gsap.to(element, {
      scale: 1.05,
      duration: 0.2,
      ease: 'power2.out'
    });
  });
  
  element.addEventListener('mouseleave', () => {
    gsap.to(element, {
      scale: 1,
      duration: 0.2,
      ease: 'power2.out'
    });
  });
}

/**
 * Gradient animation
 */
function animateGradient(elementId) {
  const element = document.getElementById(elementId);
  if (!element) return;
  
  gsap.to(element, {
    backgroundPosition: '200% 0',
    duration: 3,
    repeat: -1,
    ease: 'none'
  });
}

/**
 * Stagger animation for grid items
 */
function staggerAnimation(containerSelector, itemSelector, delay = 0.08) {
  const containers = document.querySelectorAll(containerSelector);
  
  containers.forEach(container => {
    const items = container.querySelectorAll(itemSelector);
    gsap.fromTo(items,
      { 
        opacity: 0,
        y: 15
      },
      {
        opacity: 1,
        y: 0,
        duration: 0.5,
        stagger: delay,
        ease: 'power2.out'
      }
    );
  });
}

/**
 * Splash/burst effect (for action completions)
 */
function burstAnimation(x, y) {
  // Create temporary particles
  const colors = ['#2a9d8f', '#1a6b8a', '#4ecdc4'];
  
  for (let i = 0; i < 8; i++) {
    const particle = document.createElement('div');
    particle.style.position = 'fixed';
    particle.style.pointerEvents = 'none';
    particle.style.width = '8px';
    particle.style.height = '8px';
    particle.style.borderRadius = '50%';
    particle.style.background = colors[Math.floor(Math.random() * colors.length)];
    particle.style.left = x + 'px';
    particle.style.top = y + 'px';
    document.body.appendChild(particle);
    
    const angle = (Math.PI * 2 * i) / 8;
    const distance = 100;
    
    gsap.to(particle, {
      x: Math.cos(angle) * distance,
      y: Math.sin(angle) * distance,
      opacity: 0,
      duration: 0.6,
      ease: 'power2.out',
      onComplete: () => particle.remove()
    });
  }
}

/**
 * Loading spinner animation
 */
function createSpinner(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  
  const spinner = document.createElement('div');
  spinner.innerHTML = `
    <div style="
      width: 40px;
      height: 40px;
      border: 3px solid #e0e8f0;
      border-top: 3px solid #2a9d8f;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 20px auto;
    "></div>
    <style>
      @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
      }
    </style>
  `;
  container.appendChild(spinner);
}

/**
 * Tooltip animation
 */
function showTooltip(element, text, duration = 2000) {
  const tooltip = document.createElement('div');
  tooltip.textContent = text;
  tooltip.style.cssText = `
    position: fixed;
    background: rgba(26, 58, 74, 0.95);
    color: #fff;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 12px;
    pointer-events: none;
    font-weight: 500;
    z-index: 10000;
    backdrop-filter: blur(4px);
  `;
  
  document.body.appendChild(tooltip);
  
  const rect = element.getBoundingClientRect();
  tooltip.style.left = (rect.left + rect.width / 2) + 'px';
  tooltip.style.top = (rect.top - 40) + 'px';
  tooltip.style.transform = 'translateX(-50%)';
  
  gsap.fromTo(tooltip,
    { opacity: 0, y: 10 },
    { opacity: 1, y: 0, duration: 0.3, ease: 'power2.out' }
  );
  
  setTimeout(() => {
    gsap.to(tooltip, {
      opacity: 0,
      y: -10,
      duration: 0.3,
      ease: 'power2.in',
      onComplete: () => tooltip.remove()
    });
  }, duration);
}

/**
 * Initialize all animations on page load
 */
document.addEventListener('DOMContentLoaded', () => {
  // Add hover effects to buttons
  document.querySelectorAll('.btn-primary').forEach(btn => {
    btn.addEventListener('mouseenter', () => {
      gsap.to(btn, { duration: 0.2, scale: 1.02 });
    });
    btn.addEventListener('mouseleave', () => {
      gsap.to(btn, { duration: 0.2, scale: 1 });
    });
  });

  // Add hover effects to stat cards
  document.querySelectorAll('.stat-card').forEach(card => {
    card.addEventListener('mouseenter', () => {
      gsap.to(card, { duration: 0.2, y: -2, boxShadow: '0 10px 30px rgba(0,0,0,0.1)' });
    });
    card.addEventListener('mouseleave', () => {
      gsap.to(card, { duration: 0.2, y: 0, boxShadow: '0 0px 0px rgba(0,0,0,0)' });
    });
  });
});
