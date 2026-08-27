const challengeData = [
  {
    title: 'Power Lift Circuit',
    description: 'Complete 3 rounds of squats, presses, and rows.',
    xp: 140,
    difficulty: 'Hard',
    progress: 72,
    badge: 'Strength'
  },
  {
    title: '10K Step Sprint',
    description: 'Hit your 10,000-step target before dinner.',
    xp: 90,
    difficulty: 'Medium',
    progress: 52,
    badge: 'Cardio'
  },
  {
    title: 'Recovery Reset',
    description: 'Stretch for 20 minutes and hydrate 2L of water.',
    xp: 60,
    difficulty: 'Easy',
    progress: 84,
    badge: 'Recovery'
  }
];

const leaderboardData = [
  { name: 'Ava', score: '2,460 XP', color: 'linear-gradient(135deg, #7ae7c7, #7da2ff)' },
  { name: 'Miles', score: '2,330 XP', color: 'linear-gradient(135deg, #ffd166, #ff9f1c)' },
  { name: 'Zoe', score: '2,160 XP', color: 'linear-gradient(135deg, #ff88b1, #ff5d8f)' }
];

const challengeList = document.getElementById('challengeList');
const leaderboardList = document.getElementById('leaderboardList');
const xpValue = document.getElementById('xpValue');
const energyValue = document.getElementById('energyValue');
const streakCount = document.getElementById('streakCount');
const streakMeta = document.getElementById('streakMeta');
const streakProgress = document.getElementById('streakProgress');

function renderChallenges() {
  challengeList.innerHTML = challengeData
    .map(
      (challenge) => `
        <article class="challenge-item">
          <div class="challenge-copy">
            <h4>${challenge.title}</h4>
            <p>${challenge.description}</p>
            <div class="challenge-meta">
              <span class="pill">+${challenge.xp} XP</span>
              <span class="pill">${challenge.difficulty}</span>
              <span class="pill">${challenge.badge}</span>
            </div>
          </div>
          <div class="challenge-right">
            <div class="challenge-progress" style="--progress: ${challenge.progress}%">
              <span>${challenge.progress}%</span>
            </div>
            <button>Track</button>
          </div>
        </article>
      `
    )
    .join('');
}

function renderLeaderboard() {
  leaderboardList.innerHTML = leaderboardData
    .map(
      (entry, index) => `
        <li>
          <div class="leaderboard-user">
            <span class="avatar" style="background: ${entry.color};">${index + 1}</span>
            <div>
              <strong>${entry.name}</strong>
              <small>${entry.score}</small>
            </div>
          </div>
          <strong>${index === 0 ? '🔥' : '⚡'}</strong>
        </li>
      `
    )
    .join('');
}

function bindQuickActions() {
  document.querySelectorAll('[data-action]').forEach((button) => {
    button.addEventListener('click', () => {
      const currentXp = Number(xpValue.textContent.replace(/[^\d]/g, '')) || 0;
      const currentEnergy = Number(energyValue.textContent.replace(/[^\d]/g, '')) || 0;

      const actionMap = {
        workout: { xp: 120, energy: 6 },
        walk: { xp: 60, energy: 4 },
        hydrate: { xp: 15, energy: 2 }
      };

      const action = actionMap[button.dataset.action];
      xpValue.textContent = `${currentXp + action.xp} XP`;
      energyValue.textContent = `${Math.min(currentEnergy + action.energy, 100)}%`;

      const currentStreak = Number(streakCount.textContent.match(/\d+/)?.[0] || 0);
      streakCount.textContent = `${currentStreak + 1} days`;
      streakMeta.textContent = `${Math.max(0, 10 - currentStreak)} / 10 days to elite streak`;
      streakProgress.style.width = `${Math.min((currentStreak + 1) / 10 * 100, 100)}%`;
    });
  });
}

renderChallenges();
renderLeaderboard();
bindQuickActions();
