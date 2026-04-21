/**
 * LAPA - Mental Health Dashboard
 * Patient-Side Application - SPA Architecture
 * Complete implementation according to master specification
 */

// ============================================================
// SECTION 1: STORAGE MANAGER
// ============================================================

class LAPAStorage {

  static getPatients() {
    try {
      return JSON.parse(
        localStorage.getItem('lapa_patients') || '[]'
      );
    } catch { return []; }
  }

  static savePatients(patients) {
    localStorage.setItem(
      'lapa_patients', JSON.stringify(patients)
    );
  }

  static getPatientById(id) {
    return this.getPatients().find(p => p.id === id) || null;
  }

  static getPatientByUsername(username) {
    return this.getPatients()
      .find(p => p.username === username.trim()) || null;
  }

  static savePatient(patient) {
    const patients = this.getPatients();
    const index = patients.findIndex(p => p.id === patient.id);
    if (index >= 0) {
      patients[index] = patient;
    } else {
      patients.push(patient);
    }
    this.savePatients(patients);
  }

  static getCurrentUser() {
    const id = localStorage.getItem('lapa_current_user');
    if (!id) return null;
    return this.getPatientById(id);
  }

  static setCurrentUser(id) {
    localStorage.setItem('lapa_current_user', id);
  }

  static clearCurrentUser() {
    localStorage.removeItem('lapa_current_user');
  }

  static isUsernameAvailable(username) {
    const patients = this.getPatients();
    const doctors = JSON.parse(
      localStorage.getItem('lapa_doctors') || '[]'
    );
    const allUsernames = [
      ...patients.map(p => p.username),
      ...doctors.map(d => d.username)
    ];
    return !allUsernames.includes(username.trim());
  }

  static addJournalEntry(patientId, entry) {
    const patient = this.getPatientById(patientId);
    if (!patient) return false;
    patient.journalEntries.push(entry);
    this.savePatient(patient);
    return true;
  }

  static saveWeeklyAnalysis(patientId, analysis) {
    const patient = this.getPatientById(patientId);
    if (!patient) return false;
    const idx = patient.weeklyAnalysis
      .findIndex(w => w.weekId === analysis.weekId);
    if (idx >= 0) {
      patient.weeklyAnalysis[idx] = analysis;
    } else {
      patient.weeklyAnalysis.push(analysis);
    }
    this.savePatient(patient);
    return true;
  }

  static updateBaseline(patientId, baselineData) {
    const patient = this.getPatientById(patientId);
    if (!patient) return false;
    patient.baseline = { ...patient.baseline, ...baselineData };
    this.savePatient(patient);
    return true;
  }

  static initDoctor() {
    const existing = localStorage.getItem('lapa_doctors');
    if (!existing || JSON.parse(existing).length === 0) {
      localStorage.setItem('lapa_doctors', JSON.stringify([{
        id: 'DOC_001',
        username: 'dr_priya',
        password: 'priya123',
        name: 'Dr. Priya Dharshini S P',
        department: 'Psychiatry - AI Mental Health'
      }]));
    }
  }
}

// ============================================================
// SECTION 2: AUTH MANAGER
// ============================================================

class AuthManager {

  static login(username, password) {
    if (!username || !password) {
      return {
        success: false,
        error: 'Please fill in all fields'
      };
    }

    // Check patients
    const patient = LAPAStorage.getPatientByUsername(username);
    if (patient) {
      if (patient.password === password) {
        patient.lastLogin = new Date().toISOString();
        LAPAStorage.savePatient(patient);
        LAPAStorage.setCurrentUser(patient.id);
        return { success: true, user: patient };
      } else {
        return {
          success: false,
          error: 'Incorrect password'
        };
      }
    }

    return {
      success: false,
      error: 'No account found with this username'
    };
  }

  static register(formData) {
    // Validate all required fields
    const required = [
      'username', 'password', 'confirmPassword',
      'fullName', 'age', 'gender', 'condition',
      'contactNumber'
    ];
    for (const field of required) {
      if (!formData[field] || 
          formData[field].toString().trim() === '') {
        return {
          success: false,
          error: 'Please fill in all required fields'
        };
      }
    }

    // Username length check
    if (formData.username.trim().length < 3) {
      return {
        success: false,
        error: 'Username must be at least 3 characters'
      };
    }

    // Password match check
    if (formData.password !== formData.confirmPassword) {
      return {
        success: false,
        error: 'Passwords do not match'
      };
    }

    // Password length check
    if (formData.password.length < 6) {
      return {
        success: false,
        error: 'Password must be at least 6 characters'
      };
    }

    // Age validation
    const age = parseInt(formData.age);
    if (isNaN(age) || age < 13 || age > 100) {
      return {
        success: false,
        error: 'Please enter a valid age between 13 and 100'
      };
    }

    // Username availability
    if (!LAPAStorage.isUsernameAvailable(formData.username)) {
      return {
        success: false,
        error: 'This username is already taken'
      };
    }

    // Create patient
    const newPatient = {
      id: 'PAT_' + Date.now(),
      username: formData.username.trim(),
      password: formData.password,
      profile: {
        fullName: formData.fullName.trim(),
        age: age,
        gender: formData.gender,
        condition: formData.condition,
        contactNumber: formData.contactNumber.trim(),
        emergencyContact: formData.emergencyContact || '',
        joinDate: new Date().toISOString().split('T')[0],
        assignedDoctor: 'Dr. Priya Dharshini S P'
      },
      journalEntries: [],
      weeklyAnalysis: [],
      baseline: {
        established: false,
        weeksCollected: 0,
        emotionBaseline: {},
        topicBaseline: {},
        variabilityBaseline: 0
      },
      moodHistory: [],
      gratitudeHistory: [],
      chatHistory: [],
      alerts: [],
      lastLogin: new Date().toISOString(),
      createdAt: new Date().toISOString()
    };

    LAPAStorage.savePatient(newPatient);
    LAPAStorage.setCurrentUser(newPatient.id);
    return { success: true, user: newPatient };
  }

  static isLoggedIn() {
    return LAPAStorage.getCurrentUser() !== null;
  }

  static logout() {
    LAPAStorage.clearCurrentUser();
    forceShowPage('login');
    showToast('Logged out successfully', 'info');
  }
}

// ============================================================
// SECTION 3: ANALYSIS ENGINE
// ============================================================

class AnalysisEngine {

  static analyzeText(text) {
    const emotionWords = {
      fear: ['afraid','scared','terrified','anxious',
             'worried','nervous','panic','dread',
             'frightened','horror','phobia','stress'],
      sadness: ['sad','depressed','unhappy','miserable',
                'lonely','hopeless','grief','cry',
                'sorrow','tears','despair','empty'],
      anger: ['angry','furious','frustrated','annoyed',
              'rage','hate','irritated','mad',
              'bitter','resentful','hostile'],
      joy: ['happy','excited','grateful','wonderful',
            'love','enjoy','pleased','great',
            'joyful','blessed','content','cheerful'],
      surprise: ['shocked','amazed','unexpected',
                 'suddenly','wow','unbelievable',
                 'astonished','startled']
    };

    const emotions = {
      fear: 0, sadness: 0, anger: 0,
      joy: 0, surprise: 0, neutral: 0
    };

    const words = text.toLowerCase()
      .replace(/[^a-z\s]/g, '')
      .split(/\s+/)
      .filter(w => w.length > 2);

    words.forEach(word => {
      let matched = false;
      for (const [emotion, keywords] of
           Object.entries(emotionWords)) {
        if (keywords.includes(word)) {
          emotions[emotion]++;
          matched = true;
          break;
        }
      }
    });

    const total = Object.values(emotions)
      .reduce((a, b) => a + b, 0);

    if (total === 0) {
      return {
        fear: 0, sadness: 0, anger: 0,
        joy: 0, surprise: 0, neutral: 1.0
      };
    }

    return Object.fromEntries(
      Object.entries(emotions).map(([k, v]) => [
        k, parseFloat((v / total).toFixed(3))
      ])
    );
  }

  static detectTopics(text) {
    const topicKeywords = {
      family: ['family','mother','father','sister',
               'brother','parent','children','home',
               'mom','dad','son','daughter','spouse',
               'husband','wife','grandma','grandpa'],
      work: ['work','job','office','boss','colleague',
             'project','meeting','deadline','career',
             'salary','promotion','company','task'],
      health: ['health','sick','doctor','medicine',
               'pain','hospital','tired','sleep',
               'exercise','body','symptoms','therapy'],
      relationships: ['friend','partner','relationship',
                      'love','breakup','dating','trust',
                      'conflict','argue','support','miss'],
      self: ['myself','alone','thoughts','mind','feel',
             'think','believe','personal','identity',
             'confidence','worth','purpose','goal'],
      social: ['people','society','public','event',
               'party','group','community','social',
               'crowd','interact','gathering']
    };

    const topics = {};
    const lowerText = text.toLowerCase();

    for (const [topic, keywords] of
         Object.entries(topicKeywords)) {
      topics[topic] = keywords.filter(
        k => lowerText.includes(k)
      ).length;
    }

    return topics;
  }

  static detectVagueness(text) {
    const vagueWords = [
      'maybe', 'perhaps', 'kind of', 'sort of',
      'somewhat', 'probably', 'possibly', 'might',
      'could be', 'i think', 'not sure', 'i guess',
      'whatever', 'stuff', 'things', 'anyway',
      'i dont know', "i don't know", 'hard to say'
    ];
    const lowerText = text.toLowerCase();
    const found = vagueWords.filter(
      w => lowerText.includes(w)
    ).length;
    const wordCount = text.split(/\s+/).length;
    return Math.min(
      found / Math.max(wordCount / 15, 1), 1.0
    );
  }

  static getCurrentWeekNumber(patient) {
    if (!patient.profile.joinDate) return 1;
    const joinDate = new Date(patient.profile.joinDate);
    const today = new Date();
    const diffDays = Math.floor(
      (today - joinDate) / (1000 * 60 * 60 * 24)
    );
    return Math.max(1, Math.floor(diffDays / 7) + 1);
  }

  static computeWeeklyAnalysis(patient) {
    if (!patient.journalEntries ||
        patient.journalEntries.length === 0) {
      return [];
    }

    // Group entries by week
    const weekGroups = {};
    patient.journalEntries.forEach(entry => {
      const wk = entry.weekNumber;
      if (!weekGroups[wk]) weekGroups[wk] = [];
      weekGroups[wk].push(entry);
    });

    const analyses = [];

    for (const [weekNum, entries] of
         Object.entries(weekGroups)) {
      const wkNum = parseInt(weekNum);
      const allText = entries.map(e => e.text).join(' ');
      const emotions = this.analyzeText(allText);
      const topics = this.detectTopics(allText);
      const vagueness = this.detectVagueness(allText);

      let avoidanceScore = 0;
      let tsi = 0;
      let flagged = false;
      let flagReason = '';

      // Compare against baseline if ready
      if (patient.baseline.established && wkNum > 4) {
        const baseTopics = patient.baseline.topicBaseline;
        let suppressionTotal = 0;
        let topicCount = 0;

        for (const [topic, baseFreq] of
             Object.entries(baseTopics)) {
          if (baseFreq > 0) {
            const currentFreq = topics[topic] || 0;
            suppressionTotal += Math.max(
              0, (baseFreq - currentFreq) / baseFreq
            );
            topicCount++;
          }
        }

        tsi = topicCount > 0
          ? parseFloat(
              (suppressionTotal / topicCount).toFixed(2)
            )
          : 0;

        const emotionFlat = 1 - (emotions.joy || 0);
        avoidanceScore = parseFloat(
          (tsi * 0.4 + vagueness * 0.3 +
           emotionFlat * 0.3).toFixed(2)
        );

        flagged = avoidanceScore > 0.65;
        if (flagged) {
          flagReason =
            'Elevated avoidance patterns detected. ' +
            'Topic suppression and emotional flattening ' +
            'observed this week.';
        }
      }

      analyses.push({
        weekId: wkNum,
        weekLabel: 'Week ' + wkNum,
        avoidanceScore,
        topicSuppressionIndex: tsi,
        emotionalVariabilityScore: parseFloat(
          vagueness.toFixed(2)
        ),
        emotions,
        topics,
        flagged,
        flagReason,
        entryCount: entries.length
      });
    }

    // Establish baseline after 4 weeks
    const totalWeeks = Object.keys(weekGroups).length;
    if (totalWeeks >= 4 && !patient.baseline.established) {
      const baseEntries = patient.journalEntries.filter(
        e => e.weekNumber <= 4
      );
      const baseText = baseEntries.map(e => e.text).join(' ');
      LAPAStorage.updateBaseline(patient.id, {
        established: true,
        weeksCollected: 4,
        emotionBaseline: this.analyzeText(baseText),
        topicBaseline: this.detectTopics(baseText),
        variabilityBaseline: this.detectVagueness(baseText)
      });
    }

    return analyses.sort((a, b) => a.weekId - b.weekId);
  }
}

// ============================================================
// SECTION 4: NAVIGATION SYSTEM
// ============================================================

const PROTECTED_PAGES = [
  'dashboard', 'journal', 'analysis',
  'history', 'mindfulness', 'chat',
  'report', 'settings'
];

const PAGE_LOADERS = {
  dashboard:    loadDashboardData,
  journal:      loadJournalData,
  analysis:     loadAnalysisData,
  history:      loadHistoryData,
  mindfulness:  loadMindfulnessData,
  chat:         initChat,
  settings:     loadSettingsData
};

function showPage(pageId) {
  // Auth guard
  if (PROTECTED_PAGES.includes(pageId)) {
    if (!AuthManager.isLoggedIn()) {
      forceShowPage('login');
      showToast('Please login to continue', 'warning');
      return;
    }
  }
  forceShowPage(pageId);
  if (PAGE_LOADERS[pageId]) {
    try {
      PAGE_LOADERS[pageId]();
    } catch (err) {
      console.error('Page load error:', pageId, err);
    }
  }
}

function forceShowPage(pageId) {
  // Hide every page without exception
  document.querySelectorAll('.page').forEach(page => {
    page.classList.remove('active');
    page.style.display = 'none';
    page.style.opacity = '0';
  });

  const target = document.getElementById('page-' + pageId);
  if (!target) {
    console.error('Missing page div: page-' + pageId);
    return;
  }

  // Show only this page
  target.style.display = 'block';

  // Animate in
  requestAnimationFrame(() => {
    target.classList.add('active');
    target.style.transition = 'opacity 0.35s ease';
    target.style.opacity = '1';
  });

  // Update sidebar
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
    if (item.dataset.page === pageId) {
      item.classList.add('active');
    }
  });

  window.scrollTo(0, 0);
}

// ============================================================
// SECTION 5: UTILITY FUNCTIONS
// ============================================================

function showToast(message, type = 'info') {
  document.querySelectorAll('.lapa-toast')
    .forEach(t => t.remove());

  const colors = {
    success: '#10B981',
    warning: '#F59E0B',
    danger:  '#EF4444',
    info:    '#00D4FF'
  };

  const icons = {
    success: '✓',
    warning: '⚠',
    danger:  '✕',
    info:    'ℹ'
  };

  const toast = document.createElement('div');
  toast.className = 'lapa-toast';
  toast.innerHTML = `
    <span class="toast-icon">${icons[type]}</span>
    <span class="toast-message">${message}</span>
  `;
  toast.style.cssText = `
    position: fixed;
    top: 24px;
    right: 24px;
    background: ${colors[type]};
    color: white;
    padding: 14px 20px;
    border-radius: 10px;
    z-index: 99999;
    font-weight: 500;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    box-shadow: 0 8px 30px rgba(0,0,0,0.4);
    transform: translateX(120%);
    transition: transform 0.35s cubic-bezier(0.4,0,0.2,1);
    max-width: 360px;
    font-family: Inter, sans-serif;
  `;
  document.body.appendChild(toast);

  requestAnimationFrame(() => {
    toast.style.transform = 'translateX(0)';
  });

  setTimeout(() => {
    toast.style.transform = 'translateX(120%)';
    setTimeout(() => toast.remove(), 400);
  }, 3500);
}

function showLoginError(message) {
  const el = document.getElementById('login-error');
  if (!el) return;
  el.textContent = message;
  el.style.display = 'flex';
  el.style.animation = 'none';
  requestAnimationFrame(() => {
    el.style.animation = 'shake 0.4s ease';
  });
}

function clearLoginError() {
  const el = document.getElementById('login-error');
  if (el) el.style.display = 'none';
}

function showRegisterError(message) {
  const el = document.getElementById('register-error');
  if (!el) return;
  el.textContent = message;
  el.style.display = 'flex';
}

function clearRegisterError() {
  const el = document.getElementById('register-error');
  if (el) el.style.display = 'none';
}

function showUsernameStatus(available) {
  const el = document.getElementById('username-status');
  if (!el) return;
  el.style.display = 'block';
  if (available) {
    el.textContent = '✓ Username available';
    el.className = 'field-hint success';
  } else {
    el.textContent = '✕ Username already taken';
    el.className = 'field-hint error';
  }
}

function morphButtonLoading(btnId, loadingText) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.disabled = true;
  btn.dataset.originalText = btn.textContent;
  btn.innerHTML = `
    <span class="btn-spinner"></span>
    ${loadingText || 'Loading...'}
  `;
}

function morphButtonSuccess(btnId, successText) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.innerHTML = `✓ ${successText || 'Done'}`;
  btn.style.background = '#10B981';
  setTimeout(() => {
    btn.disabled = false;
    btn.innerHTML = btn.dataset.originalText || 'Submit';
    btn.style.background = '';
  }, 2500);
}

function morphButtonReset(btnId) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.disabled = false;
  btn.innerHTML = btn.dataset.originalText || 'Submit';
  btn.style.background = '';
}

function animateValue(elementId, start, end, duration) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const startTime = performance.now();
  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = start + (end - start) * eased;
    el.textContent = current.toFixed(2);
    if (progress < 1) requestAnimationFrame(update);
  }
  requestAnimationFrame(update);
}

function animateRing(ringId, percentage) {
  const ring = document.getElementById(ringId);
  if (!ring) return;
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  ring.style.strokeDasharray = circumference;
  ring.style.strokeDashoffset = circumference;
  ring.style.transition = 'none';
  requestAnimationFrame(() => {
    ring.style.transition =
      'stroke-dashoffset 1.5s cubic-bezier(0.4,0,0.2,1)';
    ring.style.strokeDashoffset =
      circumference * (1 - Math.min(percentage, 1));
    const color = percentage < 0.4 ? '#10B981'
                : percentage < 0.65 ? '#F59E0B'
                : '#EF4444';
    ring.style.stroke = color;
  });
}

function getIndicatorColor(value) {
  if (value < 0.4)  return '#10B981';
  if (value < 0.65) return '#F59E0B';
  return '#EF4444';
}

function getRiskLabel(value) {
  if (value < 0.4)  return { label: 'Normal',  cls: 'normal'  };
  if (value < 0.65) return { label: 'Watch',   cls: 'warning' };
  return                    { label: 'Flagged', cls: 'danger'  };
}

function getRandom(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function getVal(id) {
  const el = document.getElementById(id);
  return el ? el.value : '';
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value || '—';
}

function setVal(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value || '';
}

function debounce(fn, delay) {
  let timer;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

function showConfirmDialog(message, onConfirm) {
  const overlay = document.createElement('div');
  overlay.className = 'confirm-overlay';
  overlay.innerHTML = `
    <div class="confirm-dialog glass-card">
      <p class="confirm-message">${message}</p>
      <div class="confirm-actions">
        <button class="btn-ghost" id="confirm-cancel">
          Cancel
        </button>
        <button class="btn-danger" id="confirm-ok">
          Confirm
        </button>
      </div>
    </div>
  `;
  overlay.style.cssText = `
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.6);
    display: flex; align-items: center;
    justify-content: center; z-index: 99998;
    backdrop-filter: blur(4px);
  `;
  document.body.appendChild(overlay);

  const dialog = overlay.querySelector('.confirm-dialog');
  dialog.style.cssText = `
    padding: 30px; border-radius: 16px;
    max-width: 400px; width: 90%;
    transform: scale(0.8); opacity: 0;
    transition: all 0.3s cubic-bezier(0.4,0,0.2,1);
  `;

  requestAnimationFrame(() => {
    dialog.style.transform = 'scale(1)';
    dialog.style.opacity = '1';
  });

  const close = () => {
    dialog.style.transform = 'scale(0.8)';
    dialog.style.opacity = '0';
    setTimeout(() => overlay.remove(), 300);
  };

  overlay.querySelector('#confirm-cancel')
    .addEventListener('click', close);
  overlay.querySelector('#confirm-ok')
    .addEventListener('click', () => {
      close();
      onConfirm();
    });
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });
}

// ============================================================
// SECTION 6: APP STARTUP
// ============================================================

document.addEventListener('DOMContentLoaded', () => {

  // Initialize doctor account once
  LAPAStorage.initDoctor();

  // Check existing session
  const currentId = localStorage
    .getItem('lapa_current_user');

  if (currentId) {
    const user = LAPAStorage.getPatientById(currentId);
    if (user) {
      forceShowPage('dashboard');
      loadDashboardData();
    } else {
      // Stale session — clear it
      LAPAStorage.clearCurrentUser();
      forceShowPage('login');
    }
  } else {
    forceShowPage('login');
  }

  // Wire sidebar nav items
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      const page = item.dataset.page;
      if (page) showPage(page);
    });
  });

  // Wire login form
  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', function(e) {
      e.preventDefault();
      clearLoginError();
      const username = document
        .getElementById('login-username').value.trim();
      const password = document
        .getElementById('login-password').value;
      morphButtonLoading('login-btn', 'Signing in...');

      setTimeout(() => {
        const result = AuthManager.login(username, password);
        if (result.success) {
          morphButtonSuccess('login-btn', 'Welcome!');
          setTimeout(() => {
            showPage('dashboard');
          }, 600);
        } else {
          morphButtonReset('login-btn');
          showLoginError(result.error);
        }
      }, 400);
    });
  }

  // Wire register form
  const registerForm = document
    .getElementById('register-form');
  if (registerForm) {
    registerForm.addEventListener('submit', function(e) {
      e.preventDefault();
      clearRegisterError();
      const formData = {
        username:        getVal('reg-username'),
        password:        getVal('reg-password'),
        confirmPassword: getVal('reg-confirm'),
        fullName:        getVal('reg-fullname'),
        age:             getVal('reg-age'),
        gender:          getVal('reg-gender'),
        condition:       getVal('reg-condition'),
        contactNumber:   getVal('reg-contact'),
        emergencyContact:getVal('reg-emergency')
      };
      morphButtonLoading('register-btn', 'Creating...');

      setTimeout(() => {
        const result = AuthManager.register(formData);
        if (result.success) {
          morphButtonSuccess('register-btn', 'Account created!');
          showToast('Welcome to LAPA!', 'success');
          setTimeout(() => {
            showPage('dashboard');
          }, 800);
        } else {
          morphButtonReset('register-btn');
          showRegisterError(result.error);
        }
      }, 400);
    });

    // Username availability check
    const usernameInput = document
      .getElementById('reg-username');
    if (usernameInput) {
      usernameInput.addEventListener('blur', function() {
        if (this.value.trim().length >= 3) {
          const available = LAPAStorage
            .isUsernameAvailable(this.value.trim());
          showUsernameStatus(available);
        }
      });
    }

    // Password match check
    const confirmInput = document
      .getElementById('reg-confirm');
    if (confirmInput) {
      confirmInput.addEventListener('input', function() {
        const password = getVal('reg-password');
        const hint = document
          .getElementById('confirm-hint');
        if (hint) {
          if (this.value && this.value !== password) {
            hint.textContent = 'Passwords do not match';
            hint.className = 'field-hint error';
            hint.style.display = 'block';
          } else if (this.value === password) {
            hint.textContent = '✓ Passwords match';
            hint.className = 'field-hint success';
            hint.style.display = 'block';
          }
        }
      });
    }
  }

  // Wire logout button
  const logoutBtn = document.getElementById('logout-btn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      showConfirmDialog(
        'Are you sure you want to logout?',
        () => AuthManager.logout()
      );
    });
  }
});

// ============================================================
// SECTION 7: PAGE LOADERS
// ============================================================

function loadDashboardData() {
  const user = LAPAStorage.getCurrentUser();
  if (!user) return;

  // Fill patient info
  setText('patient-name', user.profile.fullName);
  setText('patient-condition', user.profile.condition);
  setText('patient-age', user.profile.age + ' yrs');
  setText('patient-joined', user.profile.joinDate);
  setText('journal-count',
    user.journalEntries.length + ' entries');

  const analyses = AnalysisEngine
    .computeWeeklyAnalysis(user);

  if (!analyses || analyses.length === 0) {
    showEmptyDashboard();
    return;
  }

  const latest = analyses[analyses.length - 1];

  // Animate indicator rings and numbers
  animateRing('as-ring', latest.avoidanceScore);
  animateRing('tsi-ring', latest.topicSuppressionIndex);
  animateRing('evs-ring', latest.emotionalVariabilityScore);
  animateValue('as-value', 0, latest.avoidanceScore, 1500);
  animateValue('tsi-value', 0,
    latest.topicSuppressionIndex, 1500);
  animateValue('evs-value', 0,
    latest.emotionalVariabilityScore, 1500);

  // Risk labels
  const asRisk = getRiskLabel(latest.avoidanceScore);
  const el = document.getElementById('as-risk-label');
  if (el) {
    el.textContent = asRisk.label;
    el.className = 'risk-badge ' + asRisk.cls;
  }

  // Baseline status
  const baselineEl = document
    .getElementById('baseline-status');
  if (baselineEl) {
    if (user.baseline.established) {
      baselineEl.textContent = 'Baseline: Ready ✓';
      baselineEl.className = 'baseline-badge ready';
    } else {
      const weeks = analyses.length;
      baselineEl.textContent =
        `Baseline: Building (${weeks}/4 weeks)`;
      baselineEl.className = 'baseline-badge building';
    }
  }

  // Alert if flagged
  if (latest.flagged) {
    showToast(
      'Avoidance pattern detected this week', 'danger'
    );
  }
}

function showEmptyDashboard() {
  const main = document.getElementById('dashboard-main');
  if (!main) return;
  main.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">📓</div>
      <h3>Welcome to LAPA</h3>
      <p>Start your mental health journey by writing
         your first journal entry. Your personal
         analysis will appear here after your
         first submission.</p>
      <button class="btn-primary"
        onclick="showPage('journal')">
        Write First Entry
      </button>
    </div>
  `;
}

function loadJournalData() {
  const user = LAPAStorage.getCurrentUser();
  if (!user) return;

  const weekNum = AnalysisEngine
    .getCurrentWeekNumber(user);
  setText('current-week-label', 'Week ' + weekNum);
  setText('total-entries',
    user.journalEntries.length + ' total entries');

  // Recent entries
  const container = document
    .getElementById('recent-entries');
  if (container) {
    const recent = [...user.journalEntries]
      .reverse().slice(0, 5);
    if (recent.length === 0) {
      container.innerHTML = `
        <div class="empty-small">
          No entries yet. Write your first one above.
        </div>
      `;
    } else {
      container.innerHTML = recent.map(entry => `
        <div class="entry-card glass-card">
          <div class="entry-header">
            <span class="entry-date">${entry.date}</span>
            <span class="entry-week">
              Week ${entry.weekNumber}
            </span>
            <span class="entry-words">
              ${entry.wordCount} words
            </span>
          </div>
          <p class="entry-preview">
            ${entry.text.substring(0, 120)}...
          </p>
        </div>
      `).join('');
    }
  }

  // Wire submit button
  const submitBtn = document.getElementById('journal-submit');
  if (submitBtn) {
    submitBtn.onclick = submitJournalEntry;
  }

  // Live analysis on typing
  const textarea = document.getElementById('journal-text');
  if (textarea) {
    textarea.addEventListener('input', debounce(() => {
      updateLiveAnalysis(textarea.value);
      updateWordCount(textarea.value);
    }, 400));
  }
}

function submitJournalEntry() {
  const user = LAPAStorage.getCurrentUser();
  if (!user) { showPage('login'); return; }

  const textarea = document.getElementById('journal-text');
  const text = textarea ? textarea.value.trim() : '';

  if (text.length < 50) {
    showToast(
      'Please write at least 50 characters', 'warning'
    );
    return;
  }

  const weekNum = AnalysisEngine
    .getCurrentWeekNumber(user);
  const entry = {
    entryId: 'ENT_' + Date.now(),
    date: new Date().toISOString().split('T')[0],
    weekNumber: weekNum,
    text: text,
    wordCount: text.split(/\s+/).filter(w => w).length,
    submittedAt: new Date().toISOString()
  };

  morphButtonLoading('journal-submit', 'Saving...');

  setTimeout(() => {
    const success = LAPAStorage
      .addJournalEntry(user.id, entry);
    if (success) {
      morphButtonSuccess('journal-submit', 'Entry Saved!');
      showToast('Journal entry saved!', 'success');
      if (textarea) textarea.value = '';
      updateWordCount('');
      updateLiveAnalysis('');
      loadJournalData();
    } else {
      morphButtonReset('journal-submit');
      showToast('Failed to save. Try again.', 'danger');
    }
  }, 500);
}

function updateWordCount(text) {
  const words = text.trim()
    ? text.trim().split(/\s+/).length : 0;
  const chars = text.length;
  const el = document.getElementById('word-count');
  if (el) el.textContent = `${words} words · ${chars} chars`;
}

function updateLiveAnalysis(text) {
  if (text.length < 20) {
    clearLiveAnalysis();
    return;
  }
  const emotions = AnalysisEngine.analyzeText(text);
  const topics = AnalysisEngine.detectTopics(text);
  const vagueness = AnalysisEngine.detectVagueness(text);

  // Update emotion bars
  for (const [emotion, value] of Object.entries(emotions)) {
    const bar = document.getElementById(
      `live-${emotion}-bar`
    );
    if (bar) {
      bar.style.width = (value * 100).toFixed(1) + '%';
      bar.style.transition = 'width 0.4s ease';
    }
    const label = document.getElementById(
      `live-${emotion}-val`
    );
    if (label) {
      label.textContent = (value * 100).toFixed(0) + '%';
    }
  }

  // Update topic pills
  const topicContainer = document
    .getElementById('live-topics');
  if (topicContainer) {
    const detected = Object.entries(topics)
      .filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1]);
    if (detected.length === 0) {
      topicContainer.innerHTML =
        '<span class="no-topics">No topics detected yet</span>';
    } else {
      topicContainer.innerHTML = detected.map(([topic, count]) =>
        `<span class="topic-pill topic-${topic}">
           ${topic} (${count})
         </span>`
      ).join('');
    }
  }

  // Update vagueness
  const vagBar = document.getElementById('vagueness-bar');
  if (vagBar) {
    vagBar.style.width = (vagueness * 100).toFixed(1) + '%';
    vagBar.style.background =
      vagueness > 0.5 ? '#EF4444'
      : vagueness > 0.3 ? '#F59E0B'
      : '#10B981';
  }
}

function clearLiveAnalysis() {
  ['fear','sadness','anger','joy','surprise','neutral']
    .forEach(em => {
      const bar = document.getElementById(`live-${em}-bar`);
      if (bar) bar.style.width = '0%';
      const val = document.getElementById(`live-${em}-val`);
      if (val) val.textContent = '0%';
    });
  const tc = document.getElementById('live-topics');
  if (tc) tc.innerHTML =
    '<span class="no-topics">Start writing to detect topics</span>';
}

function loadAnalysisData() {
  const user = LAPAStorage.getCurrentUser();
  if (!user) return;
  const analyses = AnalysisEngine.computeWeeklyAnalysis(user);

  if (!analyses || analyses.length === 0) {
    showEmptyAnalysis();
    return;
  }

  if (analyses.length < 2) {
    showInsufficientData();
    return;
  }

  const latest = analyses[analyses.length - 1];

  if (typeof renderDetailedCharts === 'function') {
    renderDetailedCharts(latest, analyses);
  }
  loadTopicCards(latest.topics,
    user.baseline.topicBaseline || {});
}

function showEmptyAnalysis() {
  const container = document.getElementById('analysis-main');
  if (!container) return;
  container.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">📊</div>
      <h3>No Analysis Data Yet</h3>
      <p>Submit journal entries to begin analysis.
         You need at least 2 weeks of entries.</p>
      <button class="btn-primary"
        onclick="showPage('journal')">
        Add Journal Entry
      </button>
    </div>
  `;
}

function showInsufficientData() {
  const container = document.getElementById('analysis-main');
  if (!container) return;
  const user = LAPAStorage.getCurrentUser();
  const weeks = user ? user.weeklyAnalysis.length : 0;
  container.innerHTML = `
    <div class="empty-state">
      <div class="progress-ring-small">
        <svg viewBox="0 0 60 60">
          <circle cx="30" cy="30" r="25"
            fill="none" stroke="rgba(255,255,255,0.1)"
            stroke-width="4"/>
          <circle cx="30" cy="30" r="25"
            fill="none" stroke="#00D4FF"
            stroke-width="4"
            stroke-dasharray="${2*Math.PI*25}"
            stroke-dashoffset="${2*Math.PI*25*(1-weeks/2)}"
            transform="rotate(-90 30 30)"/>
        </svg>
        <span>${weeks}/2</span>
      </div>
      <h3>Building Your Analysis</h3>
      <p>You have ${weeks} week${weeks !== 1 ? 's' : ''}
         of data. Need 2 weeks minimum for comparison.</p>
      <button class="btn-primary"
        onclick="showPage('journal')">
        Continue Journaling
      </button>
    </div>
  `;
}

function loadTopicCards(currentTopics, baselineTopics) {
  const container = document
    .getElementById('topic-cards-grid');
  if (!container) return;

  const domains = [
    'family','work','health',
    'relationships','self','social'
  ];
  const icons = {
    family: '👨‍👩‍👧', work: '💼', health: '❤️',
    relationships: '🤝', self: '🧠', social: '👥'
  };

  container.innerHTML = domains.map(domain => {
    const current = currentTopics[domain] || 0;
    const baseline = baselineTopics[domain] || 0;
    const suppression = baseline > 0
      ? Math.max(0, (baseline - current) / baseline)
      : 0;
    const status = suppression > 0.6 ? 'suppressed'
                 : suppression > 0.3 ? 'watch'
                 : 'normal';
    const statusLabel = suppression > 0.6 ? 'Suppressed'
                      : suppression > 0.3 ? 'Watch'
                      : 'Normal';

    return `
      <div class="topic-card glass-card status-${status}">
        <div class="topic-card-header">
          <span class="topic-icon">${icons[domain]}</span>
          <h3>${domain.charAt(0).toUpperCase() +
               domain.slice(1)}</h3>
          <span class="topic-status-badge ${status}">
            ${statusLabel}
          </span>
        </div>
        <div class="topic-metrics">
          <div class="metric-row">
            <span>Current week</span>
            <span>${current} mentions</span>
          </div>
          <div class="metric-row">
            <span>Baseline</span>
            <span>${baseline > 0 ? baseline + ' mentions'
                                 : 'Not established'}</span>
          </div>
          <div class="topic-bar">
            <div class="topic-bar-fill"
              style="width:${Math.min(current * 20, 100)}%;
                     background:${
                       status === 'suppressed' ? '#EF4444'
                       : status === 'watch' ? '#F59E0B'
                       : '#10B981'
                     }">
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function loadHistoryData() {
  const user = LAPAStorage.getCurrentUser();
  if (!user) return;
  const analyses = AnalysisEngine.computeWeeklyAnalysis(user);

  const timeline = document
    .getElementById('history-timeline');
  if (timeline) {
    if (!analyses || analyses.length === 0) {
      timeline.innerHTML = `
        <div class="empty-small">
          No history yet. Start journaling to see
          your progress here.
        </div>
      `;
    } else {
      timeline.innerHTML = analyses.map(week => `
        <div class="timeline-node ${week.flagged
          ? 'flagged' : ''}">
          <div class="timeline-dot" style="background:${
            getIndicatorColor(week.avoidanceScore)
          }"></div>
          <div class="timeline-content glass-card">
            <h4>${week.weekLabel}</h4>
            <div class="timeline-metrics">
              <span>AS: ${week.avoidanceScore}</span>
              <span>TSI: ${week.topicSuppressionIndex}</span>
              <span>EVS: ${week.emotionalVariabilityScore}</span>
            </div>
            <div class="timeline-entries">
              ${week.entryCount} journal entries
            </div>
            ${week.flagged ? `
              <div class="timeline-flag">
                ⚠ ${week.flagReason}
              </div>
            ` : ''}
          </div>
        </div>
      `).join('');
    }
  }

  const table = document.getElementById('history-table-body');
  if (table && analyses) {
    table.innerHTML = analyses.map(week => `
      <tr class="${week.flagged ? 'row-flagged' : ''}">
        <td>${week.weekLabel}</td>
        <td style="color:${
          getIndicatorColor(week.avoidanceScore)
        }">${week.avoidanceScore}</td>
        <td>${week.topicSuppressionIndex}</td>
        <td>${week.emotionalVariabilityScore}</td>
        <td>${week.entryCount}</td>
        <td>${week.flagged
          ? '<span class="badge-danger">Flagged</span>'
          : '<span class="badge-success">Normal</span>'}</td>
      </tr>
    `).join('');
  }
}

function loadSettingsData() {
  const user = LAPAStorage.getCurrentUser();
  if (!user) return;
  setVal('settings-name', user.profile.fullName);
  setVal('settings-contact', user.profile.contactNumber);
  setVal('settings-emergency', user.profile.emergencyContact);
  setText('settings-username', user.username);
  setText('settings-condition', user.profile.condition);
  setText('settings-doctor', user.profile.assignedDoctor);
  setText('settings-joined', user.profile.joinDate);

  const saveBtn = document.getElementById('settings-save');
  if (saveBtn) {
    saveBtn.onclick = saveSettings;
  }
}

function saveSettings() {
  const user = LAPAStorage.getCurrentUser();
  if (!user) return;
  user.profile.fullName = getVal('settings-name') ||
    user.profile.fullName;
  user.profile.contactNumber = getVal('settings-contact') ||
    user.profile.contactNumber;
  user.profile.emergencyContact =
    getVal('settings-emergency') ||
    user.profile.emergencyContact;

  const newPass = getVal('settings-new-password');
  const confirmPass = getVal('settings-confirm-password');
  const currentPass = getVal('settings-current-password');

  if (newPass) {
    if (currentPass !== user.password) {
      showToast('Current password is incorrect', 'danger');
      return;
    }
    if (newPass !== confirmPass) {
      showToast('New passwords do not match', 'danger');
      return;
    }
    if (newPass.length < 6) {
      showToast('Password must be 6+ characters', 'warning');
      return;
    }
    user.password = newPass;
  }

  LAPAStorage.savePatient(user);
  showToast('Settings saved successfully!', 'success');
}

// ============================================================
// SECTION 8: MINDFULNESS PAGE
// ============================================================

function loadMindfulnessData() {
  const user = LAPAStorage.getCurrentUser();
  if (!user) return;

  // Show affirmation
  if (typeof nextAffirmation === 'function') {
    nextAffirmation(false);
  }

  // Load gratitude history
  loadGratitudeHistory();

  // Load mood history chart
  if (user.moodHistory && user.moodHistory.length > 0) {
    if (typeof renderMoodChart === 'function') {
      renderMoodChart(user.moodHistory);
    }
  }
}

const AFFIRMATIONS = [
  "I am worthy of love and healing.",
  "Every day I grow stronger and more resilient.",
  "My feelings are valid and I honor them fully.",
  "I choose peace over anxiety, one breath at a time.",
  "I am making progress, even when I cannot see it.",
  "I deserve rest, care, and compassion.",
  "I am not my thoughts. I am the observer.",
  "Healing is not linear and that is okay.",
  "I trust the process of my healing journey.",
  "I am enough exactly as I am today.",
  "This feeling will pass. I have survived before.",
  "I reach out for help when I need it. That is strength."
];

let affirmationIdx = 0;
let breathInterval = null;
let groundingIdx = 0;

function nextAffirmation(animate = true) {
  affirmationIdx = (affirmationIdx + 1) % AFFIRMATIONS.length;
  const el = document.getElementById('affirmation-text');
  if (!el) return;
  if (animate) {
    el.style.opacity = '0';
    el.style.transform = 'translateY(8px)';
    setTimeout(() => {
      el.textContent = AFFIRMATIONS[affirmationIdx];
      el.style.transition = 'all 0.4s ease';
      el.style.opacity = '1';
      el.style.transform = 'translateY(0)';
    }, 300);
  } else {
    el.textContent = AFFIRMATIONS[affirmationIdx];
  }
}

function startBreathing() {
  const phases = [
    { label: 'Inhale',  secs: 4, color: '#00D4FF', scale: 1.3 },
    { label: 'Hold',    secs: 7, color: '#7C3AED', scale: 1.3 },
    { label: 'Exhale',  secs: 8, color: '#10B981', scale: 1.0 }
  ];
  let phaseIdx = 0;
  let countdown = phases[0].secs;
  const btn = document.getElementById('breathing-btn');

  if (breathInterval) {
    clearInterval(breathInterval);
    breathInterval = null;
    if (btn) btn.textContent = 'Start Session';
    return;
  }

  if (btn) btn.textContent = 'Stop Session';

  function applyPhase() {
    const phase = phases[phaseIdx];
    const circle = document.getElementById('breath-circle');
    const label = document.getElementById('breath-label');
    const count = document.getElementById('breath-count');
    if (circle) {
      circle.style.borderColor = phase.color;
      circle.style.boxShadow = `0 0 30px ${phase.color}60`;
      circle.style.transform = `scale(${phase.scale})`;
      circle.style.transition = `transform ${phase.secs}s ease,
        border-color 0.5s ease`;
    }
    if (label) label.textContent = phase.label;
    if (count) count.textContent = countdown;
  }

  applyPhase();
  breathInterval = setInterval(() => {
    countdown--;
    const countEl = document.getElementById('breath-count');
    if (countEl) countEl.textContent = countdown;
    if (countdown <= 0) {
      phaseIdx = (phaseIdx + 1) % phases.length;
      countdown = phases[phaseIdx].secs;
      applyPhase();
    }
  }, 1000);
}

function selectMood(value) {
  const user = LAPAStorage.getCurrentUser();
  if (!user) return;

  document.querySelectorAll('.mood-btn').forEach(btn => {
    btn.classList.remove('selected');
    if (parseInt(btn.dataset.mood) === value) {
      btn.classList.add('selected');
      btn.style.transform = 'scale(1.15)';
      setTimeout(() => btn.style.transform = '', 300);
    }
  });

  if (!user.moodHistory) user.moodHistory = [];

  // One mood per day
  const today = new Date().toISOString().split('T')[0];
  const existing = user.moodHistory
    .findIndex(m => m.date === today);
  if (existing >= 0) {
    user.moodHistory[existing].value = value;
  } else {
    user.moodHistory.push({ date: today, value });
  }

  LAPAStorage.savePatient(user);
  showToast('Mood recorded for today!', 'success');

  if (typeof renderMoodChart === 'function') {
    renderMoodChart(user.moodHistory);
  }
}

const GROUNDING_STEPS = [
  "👀 Look around. Name 5 things you can SEE right now.",
  "✋ Notice 4 things you can TOUCH or feel physically.",
  "👂 Listen carefully. Name 3 sounds you can HEAR.",
  "👃 Take a breath. Notice 2 things you can SMELL.",
  "👅 Name 1 thing you can TASTE right now.",
  "✅ Excellent. You are present. You are safe. Well done."
];

function startGrounding() {
  groundingIdx = 0;
  showGroundingStep();
}

function showGroundingStep() {
  const el = document.getElementById('grounding-text');
  const progress = document.getElementById('grounding-progress');
  if (!el) return;

  el.style.opacity = '0';
  setTimeout(() => {
    el.textContent = GROUNDING_STEPS[groundingIdx];
    el.style.transition = 'opacity 0.4s ease';
    el.style.opacity = '1';
    if (progress) {
      progress.style.width =
        ((groundingIdx + 1) / GROUNDING_STEPS.length * 100)
        + '%';
    }
  }, 300);

  if (groundingIdx < GROUNDING_STEPS.length - 1) {
    setTimeout(() => {
      groundingIdx++;
      showGroundingStep();
    }, 5000);
  }
}

function saveGratitude() {
  const user = LAPAStorage.getCurrentUser();
  if (!user) return;

  const entries = ['g1', 'g2', 'g3'].map(id => {
    const el = document.getElementById('gratitude-' + id);
    return el ? el.value.trim() : '';
  }).filter(e => e);

  if (entries.length === 0) {
    showToast('Write at least one thing!', 'warning');
    return;
  }

  if (!user.gratitudeHistory) user.gratitudeHistory = [];
  user.gratitudeHistory.push({
    date: new Date().toISOString().split('T')[0],
    entries
  });
  LAPAStorage.savePatient(user);
  showToast('Gratitude saved! ✨', 'success');

  ['g1','g2','g3'].forEach(id => {
    const el = document.getElementById('gratitude-' + id);
    if (el) el.value = '';
  });
  loadGratitudeHistory();
}

function loadGratitudeHistory() {
  const user = LAPAStorage.getCurrentUser();
  const container = document
    .getElementById('gratitude-history');
  if (!container) return;
  if (!user || !user.gratitudeHistory ||
      user.gratitudeHistory.length === 0) {
    container.innerHTML = `
      <p class="empty-small">
        No gratitude entries yet. Start above!
      </p>
    `;
    return;
  }
  const recent = [...user.gratitudeHistory]
    .reverse().slice(0, 5);
  container.innerHTML = recent.map(g => `
    <div class="gratitude-entry-item">
      <span class="entry-date">${g.date}</span>
      ${g.entries.map(e =>
        `<p class="gratitude-line">✨ ${e}</p>`
      ).join('')}
    </div>
  `).join('');
}

// ============================================================
// SECTION 9: CHAT PAGE
// ============================================================

const BOT_RESPONSES = {
  anxious: [
    "I hear you. Anxiety can feel overwhelming. " +
    "Try this right now: breathe in for 4 counts, " +
    "hold for 4, breathe out for 4. You are safe.",
    "You are not alone in feeling this way. " +
    "Would you like to try the 5-4-3-2-1 grounding " +
    "exercise? Go to Mindfulness → Grounding.",
    "Anxiety often passes like a wave. Notice what " +
    "you feel in your body without judgment. " +
    "You are stronger than this moment."
  ],
  sad: [
    "I am sorry you are feeling this way. " +
    "Sadness is a valid emotion and it is okay " +
    "to feel it. You do not have to be okay right now.",
    "When sadness comes, try writing it down in " +
    "your journal. Sometimes putting words to " +
    "feelings helps them feel smaller.",
    "You reached out today and that takes courage. " +
    "I am here with you."
  ],
  sleep: [
    "Sleep difficulties are very common with anxiety " +
    "and depression. Try the 4-7-8 breathing technique " +
    "in Mindfulness before bed tonight.",
    "Avoid screens 30 minutes before bed if you can. " +
    "Writing in your journal to clear your mind " +
    "before sleep can also help significantly.",
    "Your body is working hard to heal. Rest is not " +
    "laziness. It is medicine."
  ],
  lonely: [
    "Loneliness is a painful experience and I am " +
    "genuinely glad you told me. Reaching out takes " +
    "real courage.",
    "Even one small connection can shift how we feel. " +
    "Could you send a simple message to one person " +
    "today, just to say hello?",
    "You are not as alone as loneliness makes you feel. " +
    "I am here. Your journal is here. " +
    "Your care team is here."
  ],
  motivation: [
    "Starting is always the hardest part. " +
    "Pick just one tiny thing today. Not a big goal. " +
    "One small, manageable step.",
    "Progress is not always visible but it is " +
    "always happening. The fact that you are here " +
    "and journaling is real progress.",
    "On the days when you cannot do much, " +
    "showing up at all counts. You are doing " +
    "better than you think."
  ],
  default: [
    "Thank you for sharing that with me. " +
    "Can you tell me a little more?",
    "I am listening. What you are feeling matters.",
    "That sounds genuinely difficult. " +
    "You are being very brave by talking about it.",
    "How long have you been feeling this way?",
    "What would make even this moment slightly " +
    "more bearable for you?",
    "You do not have to have it all figured out. " +
    "One moment at a time is enough."
  ]
};

function initChat() {
  const user = LAPAStorage.getCurrentUser();
  if (!user) return;

  const container = document.getElementById('chat-messages');
  if (!container) return;

  container.innerHTML = '';

  // Load saved history or show welcome
  if (user.chatHistory && user.chatHistory.length > 0) {
    user.chatHistory.slice(-30).forEach(msg => {
      appendMessageDOM(container, msg.text,
        msg.sender, msg.time);
    });
  } else {
    appendMessageDOM(container,
      `Hi ${user.profile.fullName.split(' ')[0]}! ` +
      "I am LAPA Assistant. I am here to support you. " +
      "How are you feeling today?",
      'bot',
      new Date().toLocaleTimeString([], {
        hour: '2-digit', minute: '2-digit'
      })
    );
  }

  container.scrollTop = container.scrollHeight;

  // Wire send button
  const sendBtn = document.getElementById('chat-send');
  if (sendBtn) sendBtn.onclick = sendChatMessage;

  // Wire Enter key
  const input = document.getElementById('chat-input');
  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
    // Auto-resize textarea
    input.addEventListener('input', function() {
      this.style.height = 'auto';
      this.style.height = this.scrollHeight + 'px';
    });
  }
}

function sendChatMessage() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  const time = new Date().toLocaleTimeString([],
    { hour: '2-digit', minute: '2-digit' }
  );
  const container = document.getElementById('chat-messages');

  appendMessageDOM(container, text, 'user', time);
  input.value = '';
  input.style.height = 'auto';

  // Hide quick replies
  const qr = document.getElementById('quick-replies');
  if (qr) qr.style.display = 'none';

  // Typing indicator
  showTypingIndicator(container);
  container.scrollTop = container.scrollHeight;

  setTimeout(() => {
    removeTypingIndicator();
    const response = getBotResponse(text);
    const botTime = new Date().toLocaleTimeString([],
      { hour: '2-digit', minute: '2-digit' }
    );
    appendMessageDOM(container, response, 'bot', botTime);
    container.scrollTop = container.scrollHeight;

    // Save both messages
    const user = LAPAStorage.getCurrentUser();
    if (user) {
      if (!user.chatHistory) user.chatHistory = [];
      user.chatHistory.push({ text, sender: 'user', time });
      user.chatHistory.push({
        text: response, sender: 'bot', time: botTime
      });
      // Keep last 100 messages only
      if (user.chatHistory.length > 100) {
        user.chatHistory = user.chatHistory.slice(-100);
      }
      LAPAStorage.savePatient(user);
    }
  }, 800 + Math.random() * 700);
}

function sendQuickReply(text) {
  const input = document.getElementById('chat-input');
  if (input) input.value = text;
  sendChatMessage();
}

function getBotResponse(text) {
  const lower = text.toLowerCase();
  if (/anxi|worried|nervous|stress|panic/.test(lower)) {
    return getRandom(BOT_RESPONSES.anxious);
  }
  if (/sad|depress|down|hopeless|empty|cry/.test(lower)) {
    return getRandom(BOT_RESPONSES.sad);
  }
  if (/sleep|insomnia|awake|tired|exhaust/.test(lower)) {
    return getRandom(BOT_RESPONSES.sleep);
  }
  if (/lone|alone|isolat|nobody|no one/.test(lower)) {
    return getRandom(BOT_RESPONSES.lonely);
  }
  if (/motivat|cant|cannot|giving up|pointless/.test(lower)) {
    return getRandom(BOT_RESPONSES.motivation);
  }
  return getRandom(BOT_RESPONSES.default);
}

function appendMessageDOM(container, text, sender, time) {
  const div = document.createElement('div');
  div.className = `chat-message ${sender}-message`;
  div.innerHTML = `
    <div class="message-bubble">${text}</div>
    <span class="message-time">${time}</span>
  `;
  div.style.opacity = '0';
  div.style.transform = 'translateY(10px)';
  container.appendChild(div);
  requestAnimationFrame(() => {
    div.style.transition = 'all 0.3s ease';
    div.style.opacity = '1';
    div.style.transform = 'translateY(0)';
  });
}

function showTypingIndicator(container) {
  const div = document.createElement('div');
  div.id = 'typing-indicator';
  div.className = 'chat-message bot-message';
  div.innerHTML = `
    <div class="message-bubble typing-bubble">
      <span></span><span></span><span></span>
    </div>
  `;
  container.appendChild(div);
}

function removeTypingIndicator() {
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

function clearChatHistory() {
  showConfirmDialog(
    'Clear all chat history?',
    () => {
      const user = LAPAStorage.getCurrentUser();
      if (user) {
        user.chatHistory = [];
        LAPAStorage.savePatient(user);
      }
      initChat();
      showToast('Chat cleared', 'info');
    }
  );
}

// ============================================================
// SECTION 10: CONFIRMATION DIALOG
// ============================================================

let confirmCallback = null;

function showConfirmation(message, onConfirm) {
  confirmCallback = onConfirm;
  const dialog = document.getElementById('confirm-dialog');
  if (dialog) {
    document.getElementById('confirm-message').textContent = message;
    dialog.style.display = 'flex';
  }
}

function confirmDialog() {
  const dialog = document.getElementById('confirm-dialog');
  if (dialog) {
    dialog.style.display = 'none';
  }
  if (confirmCallback) {
    confirmCallback();
    confirmCallback = null;
  }
}

function cancelDialog() {
  const dialog = document.getElementById('confirm-dialog');
  if (dialog) {
    dialog.style.display = 'none';
  }
  confirmCallback = null;
}