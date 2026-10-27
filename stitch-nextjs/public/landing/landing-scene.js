(function() {
  function initExplodedGearbox() {
    const container = document.getElementById('threejs-canvas-container');
    const canvas = document.getElementById('gearbox-canvas');
    if (!container || !canvas || typeof THREE === 'undefined') return;

    let width = container.clientWidth || 640;
    let height = container.clientHeight || 560;

    // Scene & Perspective Camera
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(36, width / height, 0.1, 1000);
    camera.position.set(0, 3.2, 17.5);
    camera.lookAt(0, 0, 0);

    // High performance WebGL Renderer
    const renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      alpha: true,
      antialias: true,
      powerPreference: "high-performance"
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.28;

    // Comprehensive Studio & Engineering Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.6);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0xf0f9ff, 2.8);
    keyLight.position.set(16, 22, 18);
    scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0x0284c7, 2.2);
    rimLight.position.set(-16, -8, -14);
    scene.add(rimLight);

    const fillLight = new THREE.DirectionalLight(0xffffff, 1.4);
    fillLight.position.set(-12, 14, 12);
    scene.add(fillLight);

    const pointLight = new THREE.PointLight(0x38bdf8, 2.4, 40);
    pointLight.position.set(0, 3, 7);
    scene.add(pointLight);

    // Industrial Materials
    const steelMat = new THREE.MeshStandardMaterial({
      color: 0x94a3b8,
      metalness: 0.88,
      roughness: 0.2
    });

    const chromeMat = new THREE.MeshStandardMaterial({
      color: 0xf1f5f9,
      metalness: 0.96,
      roughness: 0.12
    });

    const housingMat = new THREE.MeshStandardMaterial({
      color: 0x273444,
      metalness: 0.65,
      roughness: 0.35
    });

    const gearMat = new THREE.MeshStandardMaterial({
      color: 0xc9d1d9,
      metalness: 0.86,
      roughness: 0.22
    });

    const bronzeMat = new THREE.MeshStandardMaterial({
      color: 0xc18a54,
      metalness: 0.82,
      roughness: 0.26
    });

    const cyanMat = new THREE.MeshStandardMaterial({
      color: 0x0284c7,
      metalness: 0.4,
      roughness: 0.2
    });

    // Master Root Hierarchy
    const masterGroup = new THREE.Group();
    scene.add(masterGroup);

    // Initial slight isometric tilt
    let baseRotationX = 0.32;
    let baseRotationY = -0.45;
    masterGroup.rotation.x = baseRotationX;
    masterGroup.rotation.y = baseRotationY;

    // 1. Anchored Base Housing with reinforcement ribs (Y base: -3.8)
    const housingGroup = new THREE.Group();
    const housingCylinder = new THREE.Mesh(
      new THREE.CylinderGeometry(2.3, 2.3, 1.6, 36),
      housingMat
    );
    housingGroup.add(housingCylinder);

    const housingFlange = new THREE.Mesh(
      new THREE.CylinderGeometry(2.8, 2.8, 0.35, 36),
      housingMat
    );
    housingFlange.position.y = -0.7;
    housingGroup.add(housingFlange);

    // Reinforcement ribs around housing
    for (let r = 0; r < 4; r++) {
      const angle = (r / 4) * Math.PI * 2;
      const rib = new THREE.Mesh(
        new THREE.BoxGeometry(0.35, 1.4, 0.9),
        housingMat
      );
      rib.position.set(Math.cos(angle) * 2.1, 0, Math.sin(angle) * 2.1);
      rib.rotation.y = -angle;
      housingGroup.add(rib);
    }
    masterGroup.add(housingGroup);

    // 2. Central Shaft (Extends along vertical axis)
    const shaftGroup = new THREE.Group();
    const shaftCore = new THREE.Mesh(
      new THREE.CylinderGeometry(0.55, 0.55, 12, 32),
      chromeMat
    );
    shaftGroup.add(shaftCore);

    // Shaft splines
    for (let s = 0; s < 6; s++) {
      const sAngle = (s / 6) * Math.PI * 2;
      const spline = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 6.5, 0.12),
        steelMat
      );
      spline.position.set(Math.cos(sAngle) * 0.57, 0, Math.sin(sAngle) * 0.57);
      spline.rotation.y = -sAngle;
      shaftGroup.add(spline);
    }
    masterGroup.add(shaftGroup);

    // 3. Deep Groove Ball Bearing (outer race, inner race, cage, and balls)
    const bearingGroup = new THREE.Group();
    const outerRace = new THREE.Mesh(
      new THREE.CylinderGeometry(1.85, 1.85, 0.65, 36, 1, true),
      chromeMat
    );
    bearingGroup.add(outerRace);

    const innerRace = new THREE.Mesh(
      new THREE.CylinderGeometry(0.85, 0.85, 0.65, 36, 1, true),
      chromeMat
    );
    bearingGroup.add(innerRace);

    const cage = new THREE.Mesh(
      new THREE.TorusGeometry(1.35, 0.12, 16, 36),
      cyanMat
    );
    cage.rotation.x = Math.PI / 2;
    bearingGroup.add(cage);

    const ballCount = 9;
    for (let b = 0; b < ballCount; b++) {
      const bAngle = (b / ballCount) * Math.PI * 2;
      const ball = new THREE.Mesh(
        new THREE.SphereGeometry(0.32, 20, 20),
        chromeMat
      );
      ball.position.set(Math.cos(bAngle) * 1.35, 0, Math.sin(bAngle) * 1.35);
      bearingGroup.add(ball);
    }
    masterGroup.add(bearingGroup);

    // 4. Drive Gear (22T spur gear teeth, web cutouts, brass bushing)
    const gearGroup = new THREE.Group();
    const gearHub = new THREE.Mesh(
      new THREE.CylinderGeometry(1.7, 1.7, 0.75, 32),
      gearMat
    );
    gearGroup.add(gearHub);

    const gearBushing = new THREE.Mesh(
      new THREE.CylinderGeometry(0.9, 0.9, 0.78, 32),
      bronzeMat
    );
    gearGroup.add(gearBushing);

    const teethCount = 22;
    for (let t = 0; t < teethCount; t++) {
      const tAngle = (t / teethCount) * Math.PI * 2;
      const tooth = new THREE.Mesh(
        new THREE.BoxGeometry(0.42, 0.73, 0.22),
        steelMat
      );
      tooth.position.set(Math.cos(tAngle) * 1.84, 0, Math.sin(tAngle) * 1.84);
      tooth.rotation.y = -tAngle;
      gearGroup.add(tooth);
    }

    for (let h = 0; h < 5; h++) {
      const hAngle = (h / 5) * Math.PI * 2;
      const hole = new THREE.Mesh(
        new THREE.CylinderGeometry(0.24, 0.24, 0.8, 16),
        housingMat
      );
      hole.position.set(Math.cos(hAngle) * 1.25, 0, Math.sin(hAngle) * 1.25);
      gearGroup.add(hole);
    }
    masterGroup.add(gearGroup);

    // 5. Spacer with CuSn8 Bronze finish
    const spacerGroup = new THREE.Group();
    const spacerBody = new THREE.Mesh(
      new THREE.CylinderGeometry(0.95, 0.95, 0.65, 32),
      bronzeMat
    );
    spacerGroup.add(spacerBody);
    const spacerCollar = new THREE.Mesh(
      new THREE.CylinderGeometry(1.15, 1.15, 0.16, 32),
      bronzeMat
    );
    spacerCollar.position.y = 0.24;
    spacerGroup.add(spacerCollar);
    masterGroup.add(spacerGroup);

    // 6. Machined End Cap with collar and 8 bolt fasteners
    const endCapGroup = new THREE.Group();
    const endCapFlange = new THREE.Mesh(
      new THREE.CylinderGeometry(2.35, 2.35, 0.45, 36),
      steelMat
    );
    endCapGroup.add(endCapFlange);

    const endCapCollar = new THREE.Mesh(
      new THREE.CylinderGeometry(1.1, 1.1, 0.6, 28),
      steelMat
    );
    endCapCollar.position.y = 0.35;
    endCapGroup.add(endCapCollar);

    for (let bf = 0; bf < 8; bf++) {
      const bfAngle = (bf / 8) * Math.PI * 2;
      const bolt = new THREE.Mesh(
        new THREE.CylinderGeometry(0.15, 0.15, 0.4, 6),
        chromeMat
      );
      bolt.position.set(Math.cos(bfAngle) * 1.9, 0.3, Math.sin(bfAngle) * 1.9);
      endCapGroup.add(bolt);
    }
    masterGroup.add(endCapGroup);

    // 7. Floating Micro-Particles
    const particleCount = 45;
    const particleGeo = new THREE.BufferGeometry();
    const particlePositions = new Float32Array(particleCount * 3);
    for (let p = 0; p < particleCount * 3; p += 3) {
      particlePositions[p] = (Math.random() - 0.5) * 14;
      particlePositions[p + 1] = (Math.random() - 0.5) * 14;
      particlePositions[p + 2] = (Math.random() - 0.5) * 14;
    }
    particleGeo.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
    const particleMat = new THREE.PointsMaterial({
      color: 0x0284c7,
      size: 0.08,
      transparent: true,
      opacity: 0.55
    });
    const particles = new THREE.Points(particleGeo, particleMat);
    masterGroup.add(particles);

    // Dynamic Tracking Annotation Labels elements
    const tagDriveGear = document.getElementById('tag-drivegear');
    const tagBearing = document.getElementById('tag-bearing');
    const tagSpacer = document.getElementById('tag-spacer');
    const tagEndCap = document.getElementById('tag-endcap');

    function easeInOutCubic(t) {
      return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }

    let isDragging = false;
    let prevPointerX = 0;
    let prevPointerY = 0;
    let targetRotY = baseRotationY;
    let targetRotX = baseRotationX;
    let mouseParallaxX = 0;
    let mouseParallaxY = 0;

    const onPointerDown = (e) => {
      isDragging = true;
      prevPointerX = e.clientX || (e.touches && e.touches[0].clientX);
      prevPointerY = e.clientY || (e.touches && e.touches[0].clientY);
    };

    const onPointerMove = (e) => {
      const clientX = e.clientX || (e.touches && e.touches[0].clientX);
      const clientY = e.clientY || (e.touches && e.touches[0].clientY);

      if (isDragging) {
        const deltaX = clientX - prevPointerX;
        const deltaY = clientY - prevPointerY;
        targetRotY += deltaX * 0.007;
        targetRotX += deltaY * 0.007;
        prevPointerX = clientX;
        prevPointerY = clientY;
      }

      const rect = container.getBoundingClientRect();
      const normX = ((clientX - rect.left) / rect.width) * 2 - 1;
      const normY = ((clientY - rect.top) / rect.height) * 2 - 1;
      mouseParallaxX = normX * 0.15;
      mouseParallaxY = normY * 0.12;
    };

    const onPointerUp = () => {
      isDragging = false;
    };

    container.addEventListener('mousedown', onPointerDown);
    window.addEventListener('mousemove', onPointerMove);
    window.addEventListener('mouseup', onPointerUp);

    container.addEventListener('touchstart', onPointerDown, { passive: true });
    window.addEventListener('touchmove', onPointerMove, { passive: true });
    window.addEventListener('touchend', onPointerUp);

    const onResize = () => {
      if (!container || !renderer || !camera) return;
      width = container.clientWidth;
      height = container.clientHeight;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    window.addEventListener('resize', onResize);

    const tempVec = new THREE.Vector3();
    function projectPartToDOM(meshGroup, domElement, offsetY = 0) {
      if (!domElement) return;
      meshGroup.getWorldPosition(tempVec);
      tempVec.y += offsetY;
      tempVec.project(camera);

      if (tempVec.z > 1) {
        domElement.style.opacity = '0';
        return;
      }
      domElement.style.opacity = '1';

      const screenX = (tempVec.x * 0.5 + 0.5) * width;
      const screenY = (-(tempVec.y * 0.5) + 0.5) * height;

      domElement.style.left = `${screenX}px`;
      domElement.style.top = `${screenY}px`;
    }

    const initialT = 0.5;
    housingGroup.position.y = -3.2 - initialT * 0.6;
    bearingGroup.position.y = -1.3 - initialT * 0.4;
    gearGroup.position.y = 0.4 + initialT * 0.3;
    spacerGroup.position.y = 2.0 + initialT * 0.9;
    endCapGroup.position.y = 3.6 + initialT * 1.5;

    renderer.render(scene, camera);
    projectPartToDOM(gearGroup, tagDriveGear, 0.4);
    projectPartToDOM(bearingGroup, tagBearing, 0.3);
    projectPartToDOM(spacerGroup, tagSpacer, -0.4);
    projectPartToDOM(endCapGroup, tagEndCap, -0.4);

    const clock = new THREE.Clock();

    function renderLoop() {
      requestAnimationFrame(renderLoop);
      const elapsed = clock.getElapsedTime();

      if (!isDragging) {
        targetRotY += 0.0022;
      }

      masterGroup.rotation.y += (targetRotY + mouseParallaxX - masterGroup.rotation.y) * 0.06;
      masterGroup.rotation.x += (targetRotX + mouseParallaxY - masterGroup.rotation.x) * 0.06;

      gearGroup.rotation.y = elapsed * 0.6;
      shaftGroup.rotation.y = elapsed * 0.6;
      spacerGroup.rotation.y = elapsed * 0.6;

      const cycle = (Math.sin(elapsed * 0.85) + 1) / 2;
      const easedSeparation = easeInOutCubic(cycle);

      housingGroup.position.y = -3.2 - easedSeparation * 0.8;
      bearingGroup.position.y = -1.3 - easedSeparation * 0.5;
      gearGroup.position.y = 0.4 + easedSeparation * 0.4;
      spacerGroup.position.y = 2.0 + easedSeparation * 1.1;
      endCapGroup.position.y = 3.6 + easedSeparation * 1.8;

      particles.rotation.y = elapsed * 0.04;

      renderer.render(scene, camera);

      projectPartToDOM(gearGroup, tagDriveGear, 0.4);
      projectPartToDOM(bearingGroup, tagBearing, 0.3);
      projectPartToDOM(spacerGroup, tagSpacer, -0.4);
      projectPartToDOM(endCapGroup, tagEndCap, -0.4);
    }

    renderLoop();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initExplodedGearbox);
  } else {
    initExplodedGearbox();
  }
})();

// =========================================================================
// INTERACTIVE SECTION HELPERS & SCROLL-TRIGGERED MOTION
// =========================================================================

// Quick token selector
function selectToken(token) {
  const input = document.getElementById('passport-search-input');
  if (input) input.value = token;
  const buttons = document.querySelectorAll('.token-btn');
  buttons.forEach(btn => {
    if (btn.textContent.trim() === token) {
      btn.className = 'token-btn active-token px-2.5 py-1 rounded border border-brand-cyan bg-sky-100 text-sky-900 font-bold transition';
    } else {
      btn.className = 'token-btn px-2.5 py-1 rounded border border-slate-200 bg-white hover:border-brand-cyan hover:text-brand-cyan transition text-slate-600';
    }
  });
}

// Digital twin wireframe toggle
document.addEventListener('DOMContentLoaded', () => {
  const wireBtn = document.getElementById('toggle-wireframe-btn');
  const twinSvg = document.getElementById('digital-twin-svg');
  let isWire = false;
  if (wireBtn && twinSvg) {
    wireBtn.addEventListener('click', () => {
      isWire = !isWire;
      if (isWire) {
        wireBtn.textContent = 'MODE: WIREFRAME';
        wireBtn.classList.add('bg-sky-100', 'border-sky-400', 'text-sky-900');
        twinSvg.style.filter = 'drop-shadow(0 0 8px rgba(56, 189, 248, 0.8))';
      } else {
        wireBtn.textContent = 'MODE: SOLID';
        wireBtn.classList.remove('bg-sky-100', 'border-sky-400', 'text-sky-900');
        twinSvg.style.filter = 'none';
      }
    });
  }

  // Genealogy trace mode buttons
  const modeBtns = document.querySelectorAll('.mode-btn');
  modeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      modeBtns.forEach(b => {
        b.classList.remove('bg-sky-100', 'text-sky-900', 'font-bold', 'border-sky-400');
        b.classList.add('bg-white', 'text-slate-700');
      });
      btn.classList.add('bg-sky-100', 'text-sky-900', 'font-bold', 'border-sky-400');
      btn.classList.remove('bg-white', 'text-slate-700');
    });
  });

  // IntersectionObserver for Scroll-Triggered Reveals
  const revealElements = document.querySelectorAll('.reveal-item');
  if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const observer = new IntersectionObserver((entries, obs) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');
          obs.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.12,
      rootMargin: '0px 0px -40px 0px'
    });

    revealElements.forEach(el => observer.observe(el));
  } else {
    revealElements.forEach(el => el.classList.add('revealed'));
  }
});

// Audit ledger filter function
function filterAudit(category) {
  const rows = document.querySelectorAll('#audit-table-body tr');
  const buttons = document.querySelectorAll('.audit-filter-btn');
  
  buttons.forEach(btn => {
    btn.className = 'audit-filter-btn px-3 py-1.5 rounded border border-slate-200 bg-white text-slate-700 hover:border-slate-300';
  });
  
  if (event && event.target) {
    event.target.className = 'audit-filter-btn px-3 py-1.5 rounded border border-slate-900 bg-slate-900 text-white font-semibold';
  }

  rows.forEach(row => {
    const status = row.getAttribute('data-status');
    if (category === 'all' || status === category) {
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  });
}
