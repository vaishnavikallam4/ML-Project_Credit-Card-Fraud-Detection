const AUTH_ENDPOINT = '/api/auth';
const state = {
  token: localStorage.getItem('veloraToken') || '',
  user: JSON.parse(localStorage.getItem('veloraUser') || 'null'),
};

const authScreen = document.getElementById('authScreen');
const dashboardScreen = document.getElementById('dashboardScreen');
const loginForm = document.getElementById('loginForm');
const registerForm = document.getElementById('registerForm');
const tabButtons = document.querySelectorAll('.tab-button');
const overviewGrid = document.getElementById('overviewGrid');
const accountList = document.getElementById('accountList');
const cardList = document.getElementById('cardList');
const transactionList = document.getElementById('transactionList');
const alertList = document.getElementById('alertList');
const caseList = document.getElementById('caseList');
const notificationList = document.getElementById('notificationList');
const alertCount = document.getElementById('alertCount');
const transactionForm = document.getElementById('transactionForm');
const analyticsPanel = document.getElementById('analyticsPanel');
const welcomeTitle = document.getElementById('welcomeTitle');
const refreshDataBtn = document.getElementById('refreshDataBtn');
const logoutBtn = document.getElementById('logoutBtn');
const toggleAccountFormBtn = document.getElementById('toggleAccountForm');
const toggleCardFormBtn = document.getElementById('toggleCardForm');
const accountForm = document.getElementById('accountForm');
const cardForm = document.getElementById('cardForm');
const adminDirectoryPanel = document.getElementById('adminDirectoryPanel');
const adminDirectoryList = document.getElementById('adminDirectoryList');
const adminCustomerDetail = document.getElementById('adminCustomerDetail');
const adminOverviewChart = document.getElementById('adminOverviewChart');
const adminCustomerSearch = document.getElementById('adminCustomerSearch');
const adminTransactionFilters = document.getElementById('adminTransactionFilters');
const adminHomeView = document.getElementById('adminHomeView');
const adminProfileView = document.getElementById('adminProfileView');
const customerWorkspace = document.getElementById('customerWorkspace');
const adminProfileCases = document.getElementById('adminProfileCases');
const customerConversation = document.getElementById('customerConversation');
const customerMessageForm = document.getElementById('customerMessageForm');
const adminConversation = document.getElementById('adminConversation');
const adminMessageForm = document.getElementById('adminMessageForm');
let currentTransactions = [];
let currentAdminUsers = [];
let currentCards = [];
let currentCases = [];
let selectedAdminUserId = null;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function transactionDirection(transaction) {
  if (transaction.direction) return transaction.direction;
  return ['credit', 'credited', 'deposit', 'salary', 'refund', 'incoming'].includes(
    String(transaction.transaction_type || '').trim().toLowerCase(),
  ) ? 'CREDIT' : 'DEBIT';
}

function phoneAlertStatus(status) {
  if (status === 'ACCEPTED') return 'accepted by MSG91; handset delivery is not confirmed';
  if (status === 'FAILED') return 'not sent; check the phone number and MSG91 settings';
  if (status === 'SIMULATED') return 'simulated only; no SMS was sent';
  return String(status || 'delivery status unavailable').toLowerCase();
}

const setAuthTab = (tab) => {
  tabButtons.forEach((button) => {
    button.classList.toggle('active', button.dataset.tab === tab);
  });
  loginForm.classList.toggle('active', tab === 'login');
  registerForm.classList.toggle('active', tab === 'register');
};

tabButtons.forEach((button) => {
  button.addEventListener('click', () => setAuthTab(button.dataset.tab));
});

async function apiRequest(url, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  const data = await response.json().catch(() => ({}));
  const invalidJwt = response.status === 422 && typeof data.msg === 'string';
  if (response.status === 401 || invalidJwt) {
    if (state.token) {
      clearSession();
      renderAuthLayout();
      throw new Error('Your session is invalid or expired. Please log in again.');
    }
    throw new Error(data.message || data.msg || 'Invalid login details.');
  }

  if (!response.ok) {
    throw new Error(data.message || data.msg || 'Request failed');
  }

  return data;
}

function saveSession(user, token) {
  state.user = user;
  state.token = token;
  localStorage.setItem('veloraToken', token);
  localStorage.setItem('veloraUser', JSON.stringify(user));
}

function clearSession() {
  state.user = null;
  state.token = '';
  selectedAdminUserId = null;
  localStorage.removeItem('veloraToken');
  localStorage.removeItem('veloraUser');
}

function renderAuthLayout() {
  if (state.user && state.token) {
    authScreen.classList.add('hidden');
    dashboardScreen.classList.remove('hidden');
    welcomeTitle.textContent = `Welcome, ${state.user.name}`;
    document.getElementById('dashboardRoleLabel').textContent = state.user.role === 'BANK_ADMIN'
      ? 'Security operations'
      : 'Customer dashboard';
    loadDashboard();
  } else {
    authScreen.classList.remove('hidden');
    dashboardScreen.classList.add('hidden');
  }
}

async function restoreSession(showError = false) {
  if (!state.token) {
    state.user = null;
    renderAuthLayout();
    return;
  }

  try {
    const result = await apiRequest(`${AUTH_ENDPOINT}/me`);
    state.user = result.user;
    localStorage.setItem('veloraUser', JSON.stringify(result.user));
    renderAuthLayout();
  } catch (error) {
    clearSession();
    renderAuthLayout();
    console.error('Saved session could not be verified:', error);
    if (showError) throw error;
  }
}

async function handleLogin(event) {
  event.preventDefault();
  clearSession();
  const loginIdentifier = document.getElementById('loginIdentifier').value.trim();
  const password = document.getElementById('loginPassword').value;
  const payload = loginIdentifier.includes('@') ? { email: loginIdentifier, password } : { phone: loginIdentifier, password };

  try {
    const result = await apiRequest(`${AUTH_ENDPOINT}/login`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    saveSession(result.user, result.access_token);
    await restoreSession(true);
  } catch (error) {
    alert(error.message);
  }
}

async function handleRegister(event) {
  event.preventDefault();
  const payload = {
    name: document.getElementById('registerName').value.trim(),
    email: document.getElementById('registerEmail').value.trim(),
    phone: document.getElementById('registerPhone').value.trim(),
    password: document.getElementById('registerPassword').value,
    address: document.getElementById('registerAddress').value.trim(),
  };

  try {
    const result = await apiRequest(`${AUTH_ENDPOINT}/register`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    alert(result.message || 'Account created successfully');
    setAuthTab('login');
  } catch (error) {
    alert(error.message);
  }
}

async function loadDashboard() {
  if (!state.user || !state.token) {
    return;
  }

  try {
    const [accounts, cards, transactions, alerts, notifications, cases, adminUsers] = await Promise.all([
      apiRequest('/api/accounts'),
      apiRequest('/api/cards'),
      apiRequest('/api/transactions'),
      apiRequest('/api/alerts'),
      state.user.role === 'CUSTOMER' ? apiRequest('/api/notifications') : Promise.resolve({ notifications: [] }),
      apiRequest('/api/cases'),
      state.user.role === 'BANK_ADMIN' ? apiRequest('/api/admin/users') : Promise.resolve({ users: [] }),
    ]);

    renderOverview(state.user.role, accounts.accounts || [], cards.cards || [], transactions.transactions || [], alerts.alerts || [], cases.cases || [], adminUsers.users || []);
    renderAnalytics(state.user.role, accounts.accounts || [], cards.cards || [], transactions.transactions || [], alerts.alerts || [], cases.cases || []);
    renderAccounts(accounts.accounts || []);
    renderCards(cards.cards || []);
    currentCards = cards.cards || [];
    currentTransactions = transactions.transactions || [];
    currentCases = cases.cases || [];
    renderTransactions(currentTransactions);
    renderAlerts(alerts.alerts || []);
    renderNotifications(notifications.notifications || []);
    renderCases(currentCases);
    renderCustomerMessageOptions(currentCases, currentCards);
    if (state.user.role === 'CUSTOMER') {
      await loadCustomerConversation();
    }
    currentAdminUsers = adminUsers.users || [];
    renderAdminDirectory(currentAdminUsers, currentTransactions);
    if (state.user.role === 'BANK_ADMIN' && selectedAdminUserId) {
      await loadAdminCustomerDetail(selectedAdminUserId, false);
    }
    applyRoleView(state.user.role);
  } catch (error) {
    console.error(error);
    dashboardScreen.dataset.error = error.message;
    alert(error.message);
  }
}

function renderOverview(role, accounts, cards, transactions, alerts, cases, customers = []) {
  const totalBalance = accounts.reduce((sum, account) => sum + Number(account.balance || 0), 0);
  const highRisk = transactions.filter((tx) => ['MEDIUM', 'HIGH'].includes(tx.risk_level)).length;
  const openAlerts = alerts.filter((alert) => alert.status === 'OPEN').length;
  const caseCount = cases.length;

  const metrics = role === 'BANK_ADMIN'
    ? [
        { label: 'Customers', value: customers.length },
        { label: 'Accounts', value: accounts.length },
        { label: 'Card count', value: cards.length },
        { label: 'Risk events', value: highRisk },
        { label: 'Fraud cases', value: caseCount },
      ]
    : [
        { label: 'Portfolio', value: `₹${totalBalance.toLocaleString()}` },
        { label: 'Cards', value: cards.length },
        { label: 'Risk events', value: highRisk },
        { label: 'Fraud alerts', value: alerts.length },
      ];

  overviewGrid.innerHTML = metrics.map((metric) => `
    <div class="stat-card">
      <span>${metric.label}</span>
      <strong>${metric.value}</strong>
    </div>
  `).join('');
}

function applyRoleView(role) {
  const isCustomer = role === 'CUSTOMER';
  const isAdmin = role === 'BANK_ADMIN';
  const accountPanel = document.getElementById('toggleAccountForm')?.closest('.panel');
  const cardPanel = document.getElementById('toggleCardForm')?.closest('.panel');
  const transactionForm = document.getElementById('transactionForm');
  const casesHeading = document.getElementById('casesHeading');

  if (accountPanel) accountPanel.style.display = isCustomer ? 'block' : 'none';
  if (cardPanel) cardPanel.style.display = isCustomer ? 'block' : 'none';
  if (casesHeading) casesHeading.textContent = isAdmin ? 'Investigation queue' : 'Your fraud cases';

  if (transactionForm) {
    if (!isCustomer) {
      transactionForm.classList.add('hidden');
    } else {
      transactionForm.classList.remove('hidden');
    }
  }

  if (adminDirectoryPanel) {
    adminDirectoryPanel.classList.toggle('hidden', !isAdmin);
  }
  if (adminHomeView) {
    adminHomeView.classList.toggle('hidden', isAdmin && Boolean(selectedAdminUserId));
  }
  if (customerWorkspace) {
    customerWorkspace.classList.toggle('hidden', isAdmin);
  }
  if (adminProfileView) {
    adminProfileView.classList.toggle('hidden', !isAdmin || !selectedAdminUserId);
  }
  if (adminTransactionFilters) {
    adminTransactionFilters.classList.toggle('hidden', !isAdmin);
  }
}

function renderAnalytics(role, accounts, cards, transactions, alerts, cases) {
  const totalBalance = accounts.reduce((sum, account) => sum + Number(account.balance || 0), 0);
  const riskSignals = transactions.filter((tx) => ['MEDIUM', 'HIGH'].includes(tx.risk_level)).length;
  const totalRisk = transactions.reduce((sum, tx) => sum + Number(tx.fraud_probability || 0), 0);
  const avgRisk = transactions.length ? (totalRisk / transactions.length) * 100 : 0;
  const resolvedCases = cases.filter((caseItem) => ['CONFIRMED_FRAUD', 'FALSE_ALARM'].includes(caseItem.case_status)).length;
  const openCases = cases.filter((caseItem) => ['OPEN', 'INVESTIGATING'].includes(caseItem.case_status)).length;
  const openAlerts = alerts.filter((alert) => alert.status === 'OPEN').length;

  const metrics = role === 'CUSTOMER'
    ? [
        { label: 'Portfolio value', value: `₹${totalBalance.toLocaleString()}`, trend: 'Across linked accounts' },
        { label: 'Risk events', value: String(riskSignals), trend: 'Medium/high activity' },
        { label: 'Fraud alerts', value: String(alerts.length), trend: `${openAlerts} open for review` },
        { label: 'Average model risk', value: `${Math.round(avgRisk)}%`, trend: 'Across scored transactions' },
      ]
    : [
        { label: 'Open cases', value: String(openCases), trend: 'Investigation queue' },
        { label: 'Risk events', value: String(riskSignals), trend: 'Medium/high activity' },
        { label: 'Resolved cases', value: String(resolvedCases), trend: 'Recorded outcomes' },
        { label: 'Transactions scored', value: String(transactions.length), trend: 'Recorded customer activity' },
      ];

  if (analyticsPanel) {
    analyticsPanel.innerHTML = `
      <div class="panel-header">
        <h4>${role === 'CUSTOMER' ? 'Portfolio analytics' : 'Operations analytics'}</h4>
      </div>
      <div class="analytics-grid">
        ${metrics.map((metric) => `
          <div class="analytic-card">
            <span class="label">${metric.label}</span>
            <span class="value">${metric.value}</span>
            <div class="trend">↗ ${metric.trend}</div>
            <div class="bar-track"><div class="bar-fill" style="width: ${Math.min(100, (Number(metric.value.toString().replace(/[^0-9.]/g, '')) || 0) + 15)}%"></div></div>
          </div>
        `).join('')}
      </div>
    `;
  }
}

function renderAccounts(accounts) {
  accountList.innerHTML = accounts.length
    ? accounts.map((account) => `
      <div class="info-item" data-account-id="${account.account_id}">
        <span class="item-label">${account.account_type}</span>
        <span class="item-value">${account.account_number}</span>
        <span class="item-label">Available balance</span>
        <span class="item-value">₹${Number(account.balance || 0).toLocaleString()}</span>
      </div>
    `).join('')
    : '<div class="info-item"><span class="item-value">No active accounts yet.</span></div>';
}

function renderCards(cards) {
  const transactionCard = document.getElementById('transactionCardId');
  if (transactionCard) {
    transactionCard.innerHTML = `
      <option value="">Choose an active card</option>
      ${cards.filter((card) => card.status === 'ACTIVE').map((card) => `
        <option value="${card.card_id}">${escapeHtml(card.card_type)} ending ${escapeHtml(card.last_four)} · Card ${card.card_id}</option>
      `).join('')}
    `;
  }

  cardList.innerHTML = cards.length
    ? cards.map((card) => `
      <div class="card-item">
        <div class="card-top">
          <span>${card.card_type}</span>
          <span class="badge ${card.status === 'ACTIVE' ? 'low' : 'status'}">${card.status}</span>
        </div>
        <div class="card-chip"></div>
        <div class="card-number">•••• ${card.last_four}</div>
        <div class="card-meta">
          <span>Card ${card.card_id}</span>
          <span>Exp ${card.expiry_month}/${card.expiry_year}</span>
          <span>Acct ${card.account_id || '—'}</span>
        </div>
      </div>
    `).join('')
    : '<div class="info-item"><span class="item-value">No cards linked yet.</span></div>';
}

function renderTransactions(transactions) {
  const isAdmin = state.user?.role === 'BANK_ADMIN';
  const search = document.getElementById('transactionSearch')?.value.trim().toLowerCase() || '';
  const direction = document.getElementById('transactionDirection')?.value || 'ALL';
  const risk = document.getElementById('transactionRisk')?.value || 'ALL';
  const filteredTransactions = transactions.filter((tx) => {
    const searchable = `${tx.customer_name || ''} ${tx.customer_email || ''} ${tx.merchant || ''} ${tx.location || ''}`.toLowerCase();
    return (!isAdmin || !search || searchable.includes(search))
      && (!isAdmin || direction === 'ALL' || transactionDirection(tx) === direction)
      && (!isAdmin || risk === 'ALL' || (tx.risk_level || 'LOW') === risk);
  });

  if (!filteredTransactions.length) {
    transactionList.innerHTML = `<div class="info-item"><span class="item-value">${transactions.length ? 'No transactions match these filters.' : 'No transactions recorded yet.'}</span></div>`;
    return;
  }

  transactionList.innerHTML = `
    <div class="transaction-row ${isAdmin ? 'admin' : ''} header">
      ${isAdmin ? '<span>Customer</span>' : ''}
      <span>Merchant</span>
      <span>Flow</span>
      <span>Amount</span>
      <span>Risk</span>
      <span>Status</span>
    </div>
    ${filteredTransactions.map((tx) => {
      const reviewStatus = tx.customer_review_status;
      const reviewControls = !isAdmin && tx.status === 'AUTHORIZED' && !reviewStatus
        ? `
          <div class="transaction-review-actions">
            <button class="yes" data-transaction-id="${tx.transaction_id}" data-transaction-response="YES">Yes, it was me</button>
            <button class="no" data-transaction-id="${tx.transaction_id}" data-transaction-response="NO">Report fraud</button>
          </div>
        `
        : reviewStatus === 'CONFIRMED'
          ? '<span class="small-muted">Confirmed as yours</span>'
          : reviewStatus === 'REPORTED'
            ? '<span class="small-muted">Reported to the bank</span>'
            : '';
      return `
        <div class="transaction-row ${isAdmin ? 'admin' : ''}">
          ${isAdmin ? `<span>${escapeHtml(tx.customer_name || tx.customer_email || `User ${tx.user_id}`)}</span>` : ''}
          <span>${escapeHtml(tx.merchant || 'Unknown merchant')}</span>
          <span>${transactionDirection(tx)}</span>
          <span>₹${Number(tx.amount || 0).toLocaleString()}</span>
          <span><span class="badge ${tx.risk_level === 'HIGH' ? 'high' : tx.risk_level === 'MEDIUM' ? 'medium' : 'low'}">${tx.risk_level || 'LOW'}</span></span>
          <span>
            ${escapeHtml(tx.status || 'PENDING')}
            ${reviewControls}
          </span>
        </div>
      `;
    }).join('')}
  `;

  transactionList.querySelectorAll('button[data-transaction-response]').forEach((button) => {
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const result = await apiRequest(`/api/alerts/transactions/${button.dataset.transactionId}/respond`, {
          method: 'POST',
          body: JSON.stringify({ response: button.dataset.transactionResponse }),
        });
        const reviewedTransaction = filteredTransactions.find(
          (item) => String(item.transaction_id) === button.dataset.transactionId,
        );
        await loadDashboard();
        if (button.dataset.transactionResponse === 'NO' && reviewedTransaction) {
          openFraudConversation(reviewedTransaction, result.case_id);
        }
      } catch (error) {
        button.disabled = false;
        alert(error.message);
      }
    });
  });
}

function renderAlerts(alerts) {
  const openCount = alerts.filter((item) => item.status === 'OPEN').length;
  if (alertCount) {
    alertCount.textContent = `${alerts.length} ${alerts.length === 1 ? 'alert' : 'alerts'} · ${openCount} open`;
  }
  if (!alerts.length) {
    alertList.innerHTML = '<div class="info-item"><span class="item-value">No fraud alerts.</span></div>';
    return;
  }

  alertList.innerHTML = alerts.map((alert) => `
    <div class="alert-item">
      <div>
        ${state.user?.role === 'BANK_ADMIN' ? `<span class="small-muted">${escapeHtml(alert.customer_name || 'Customer')}</span>` : ''}
        <strong>${state.user?.role === 'CUSTOMER' && alert.status === 'OPEN'
          ? `Was this transaction yours? ${escapeHtml(alert.direction || 'DEBIT')} ₹${Number(alert.amount || 0).toLocaleString()} at ${escapeHtml(alert.merchant || alert.message)}.`
          : escapeHtml(alert.message)}</strong>
        ${state.user?.role === 'CUSTOMER' && alert.status === 'OPEN' ? '<p class="small-muted">If you do not recognize it, report it and the bank will temporarily hold your card.</p>' : ''}
        ${state.user?.role === 'CUSTOMER' ? `
          <div class="alert-actions">
            ${alert.status === 'OPEN' ? `
              <button class="yes" data-alert-id="${alert.alert_id}" data-transaction-id="${alert.transaction_id}" data-response="YES">Yes, it was me</button>
              <button class="no" data-alert-id="${alert.alert_id}" data-transaction-id="${alert.transaction_id}" data-response="NO">No, report fraud</button>
            ` : `<span class="badge status">${escapeHtml(alert.status)}</span>`}
          </div>
        ` : ''}
      </div>
      <span class="badge ${alert.risk_level === 'HIGH' ? 'high' : alert.risk_level === 'MEDIUM' ? 'medium' : 'low'}">${alert.risk_level}</span>
    </div>
  `).join('');

  alertList.querySelectorAll('button[data-response]').forEach((button) => {
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const result = await apiRequest(`/api/alerts/transactions/${button.dataset.transactionId}/respond`, {
          method: 'POST',
          body: JSON.stringify({ response: button.dataset.response }),
        });
        await loadDashboard();
        if (button.dataset.response === 'NO') {
          const reportedAlert = alerts.find((item) => String(item.alert_id) === button.dataset.alertId);
          if (reportedAlert) openFraudConversation(reportedAlert, result.case_id);
        }
      } catch (error) {
        button.disabled = false;
        alert(error.message);
      }
    });
  });
}

function renderNotifications(notifications) {
  if (!notifications.length) {
    notificationList.innerHTML = '<div class="info-item"><span class="item-value">No notifications.</span></div>';
    return;
  }

  notificationList.innerHTML = notifications.slice(0, 10).map((notification) => `
    <div class="notification-item">
      <div>
        ${notification.channel === 'SMS' ? `<span class="small-muted">Phone alert to ${escapeHtml(notification.phone_number || state.user?.phone || 'registered number')} · ${escapeHtml(phoneAlertStatus(notification.status))}</span>` : ''}
        <strong>${escapeHtml(notification.message)}</strong>
      </div>
      <span class="badge status">${escapeHtml(notification.status)}</span>
    </div>
  `).join('');
}

function renderCustomerMessageOptions(cases, cards) {
  const caseSelect = document.getElementById('customerMessageCase');
  const cardSelect = document.getElementById('customerMessageCard');
  if (!caseSelect || !cardSelect) return;

  const selectedCase = caseSelect.value;
  const selectedCard = cardSelect.value;
  caseSelect.innerHTML = `
    <option value="">No related case</option>
    ${cases.map((caseItem) => `<option value="${caseItem.case_id}">Case #${caseItem.case_id} · ${escapeHtml(caseItem.case_status)}</option>`).join('')}
  `;
  cardSelect.innerHTML = `
    <option value="">Select card for a hold/block request</option>
    ${cards.map((card) => `<option value="${card.card_id}">${escapeHtml(card.card_type)} ending ${escapeHtml(card.last_four)} · ${escapeHtml(card.status)}</option>`).join('')}
  `;
  if (cases.some((caseItem) => String(caseItem.case_id) === selectedCase)) caseSelect.value = selectedCase;
  if (cards.some((card) => String(card.card_id) === selectedCard)) cardSelect.value = selectedCard;
}

function renderConversation(container, messages, emptyMessage, currentRole) {
  if (!container) return;
  if (!messages.length) {
    container.innerHTML = `<div class="info-item"><span class="item-value">${escapeHtml(emptyMessage)}</span></div>`;
    return;
  }

  container.innerHTML = messages.map((message) => `
    <article class="conversation-message ${message.sender_role === currentRole ? 'customer' : 'bank'}">
      <strong>${escapeHtml(message.sender_name)} · ${escapeHtml(message.sender_role === 'CUSTOMER' ? 'Customer' : 'Bank admin')}</strong>
      <p>${escapeHtml(message.message)}</p>
      ${message.case_id ? `<span class="small-muted">Case #${message.case_id}</span>` : ''}
      ${message.requested_card_action && message.requested_card_action !== 'NONE' ? `<span class="small-muted">Card ending ${escapeHtml(message.card_last_four || '????')}: ${escapeHtml(message.requested_card_action === 'HOLD' ? 'temporary hold requested' : 'block requested')}</span>` : ''}
      <span class="small-muted">${escapeHtml(message.created_at ? new Date(message.created_at).toLocaleString() : '')}</span>
    </article>
  `).join('');
  container.scrollTop = container.scrollHeight;
}

async function loadCustomerConversation() {
  try {
    const response = await apiRequest('/api/messages');
    renderConversation(customerConversation, response.messages || [], 'No messages yet. Send a message to contact the bank team.', 'CUSTOMER');
  } catch (error) {
    console.error('Could not load customer messages:', error);
    if (customerConversation) {
      customerConversation.innerHTML = '<div class="info-item"><span class="item-value">Messages are temporarily unavailable. Your accounts, cards, transactions, and fraud alerts are still available.</span></div>';
    }
  }
}

async function loadAdminConversation(customerId) {
  try {
    const response = await apiRequest(`/api/messages/customers/${customerId}`);
    if (selectedAdminUserId === customerId) {
      renderConversation(adminConversation, response.messages || [], 'No messages yet from this customer.', 'BANK_ADMIN');
    }
  } catch (error) {
    console.error('Could not load customer messages:', error);
    if (selectedAdminUserId === customerId && adminConversation) {
      adminConversation.innerHTML = '<div class="info-item"><span class="item-value">Messages are temporarily unavailable. Customer profile and fraud case details are still available.</span></div>';
    }
  }
}

function openFraudConversation(alertItem, caseId) {
  const panel = document.querySelector('.customer-messages-panel');
  if (!panel) return;
  const transaction = currentTransactions.find((item) => Number(item.transaction_id) === Number(alertItem.transaction_id));
  const caseSelect = document.getElementById('customerMessageCase');
  const actionSelect = document.getElementById('customerMessageCardAction');
  const cardSelect = document.getElementById('customerMessageCard');
  const messageInput = document.getElementById('customerMessageText');

  if (caseSelect && caseId) caseSelect.value = String(caseId);
  if (actionSelect) actionSelect.value = 'HOLD';
  const cardId = alertItem.card_id || transaction?.card_id;
  if (cardSelect && cardId) cardSelect.value = String(cardId);
  if (messageInput) {
    messageInput.value = `I reported transaction #${alertItem.transaction_id} at ${alertItem.merchant || 'the listed merchant'} for ₹${Number(alertItem.amount || 0).toLocaleString()} as fraud. Please share the investigation details and confirm the temporary card hold.`;
  }
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  messageInput?.focus({ preventScroll: true });
}

async function sendCustomerMessage(event) {
  event.preventDefault();
  const action = document.getElementById('customerMessageCardAction').value;
  const payload = {
    message: document.getElementById('customerMessageText').value.trim(),
    case_id: document.getElementById('customerMessageCase').value || null,
    requested_card_action: action,
    card_id: action === 'NONE' ? null : document.getElementById('customerMessageCard').value || null,
  };
  try {
    await apiRequest('/api/messages', { method: 'POST', body: JSON.stringify(payload) });
    document.getElementById('customerMessageText').value = '';
    await loadCustomerConversation();
  } catch (error) {
    alert(error.message);
  }
}

async function sendAdminMessage(event) {
  event.preventDefault();
  if (!selectedAdminUserId) return;
  const messageInput = document.getElementById('adminMessageText');
  try {
    await apiRequest(`/api/messages/customers/${selectedAdminUserId}`, {
      method: 'POST',
      body: JSON.stringify({
        message: messageInput.value.trim(),
        case_id: document.getElementById('adminMessageCase')?.value || null,
      }),
    });
    messageInput.value = '';
    await loadAdminConversation(selectedAdminUserId);
  } catch (error) {
    alert(error.message);
  }
}

async function loadAdminCustomerDetail(userId, openProfile = true) {
  selectedAdminUserId = userId;
  try {
    const response = await apiRequest(`/api/admin/users/${userId}`);
    if (selectedAdminUserId !== userId) return;
    renderAdminCustomerDetail(response);
    await loadAdminConversation(userId);
    if (openProfile) {
      applyRoleView('BANK_ADMIN');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  } catch (error) {
    alert(error.message);
  }
}

function renderAdminDirectory(users, transactions) {
  if (!adminDirectoryList || !adminDirectoryPanel) {
    return;
  }

  renderAdminRiskWatch(transactions);
  const query = adminCustomerSearch?.value.trim().toLowerCase() || '';
  const visibleUsers = users.filter((user) => `${user.name} ${user.email} ${user.phone || ''}`.toLowerCase().includes(query));
  if (!visibleUsers.length) {
    selectedAdminUserId = null;
    adminDirectoryList.innerHTML = '<div class="info-item"><span class="item-value">No customer accounts found.</span></div>';
    adminCustomerDetail.innerHTML = '';
    return;
  }

  adminDirectoryList.innerHTML = visibleUsers.map((user) => `
    <div class="directory-item">
      <strong>${escapeHtml(user.name)}</strong>
      <button class="soft-button" data-admin-user-id="${user.user_id}">Open profile</button>
    </div>
  `).join('');

  adminDirectoryList.querySelectorAll('[data-admin-user-id]').forEach((button) => {
    button.addEventListener('click', () => loadAdminCustomerDetail(Number(button.dataset.adminUserId)));
  });

}

function renderAdminRiskWatch(transactions) {
  if (!adminOverviewChart) return;
  const counts = ['HIGH', 'MEDIUM', 'LOW'].map((risk) => ({
    risk,
    count: transactions.filter((tx) => (tx.risk_level || 'LOW') === risk).length,
  }));
  const maximum = Math.max(1, ...counts.map((item) => item.count));
  adminOverviewChart.innerHTML = `
    <div class="risk-watch-heading">
      <strong>Transaction risk across the bank</strong>
      <span>${transactions.length} transactions monitored</span>
    </div>
    <div class="risk-bars">
      ${counts.map((item) => `
        <div class="risk-bar-row">
          <span>${item.risk}</span>
          <div class="risk-bar-track"><div class="risk-bar-fill ${item.risk.toLowerCase()}" style="width:${Math.max(item.count ? 6 : 0, item.count / maximum * 100)}%"></div></div>
          <strong>${item.count}</strong>
        </div>
      `).join('')}
    </div>
  `;
}

function renderAdminCustomerDetail(detailPayload) {
  if (!adminCustomerDetail || !detailPayload || !detailPayload.user) {
    return;
  }

  const { user, accounts = [], cards = [], transactions = [], alerts = [], cases = [], sms_messages = [] } = detailPayload;
  const adminCaseSelect = document.getElementById('adminMessageCase');
  if (adminCaseSelect) {
    const selectedCase = adminCaseSelect.value;
    adminCaseSelect.innerHTML = `
      <option value="">General message</option>
      ${cases.map((caseItem) => `<option value="${caseItem.case_id}">Case #${caseItem.case_id} · ${escapeHtml(caseItem.case_status)}</option>`).join('')}
    `;
    if (cases.some((caseItem) => String(caseItem.case_id) === selectedCase)) {
      adminCaseSelect.value = selectedCase;
    }
  }
  adminCustomerDetail.innerHTML = `
    <div class="panel-header">
      <div>
        <p class="eyebrow">Customer profile</p>
        <h2>${escapeHtml(user.name)}</h2>
      </div>
      <span class="badge low">CUSTOMER</span>
    </div>
    <div class="detail-header">
      <div>
        <div class="small-muted">${escapeHtml(user.email)}</div>
        <div class="small-muted">${escapeHtml(user.phone || 'No phone registered')}</div>
      </div>
      <span class="badge low">${escapeHtml(user.role)}</span>
    </div>

    <div class="detail-grid">
      <div class="detail-box">
        <span class="item-label">Phone</span>
        <span class="item-value">${escapeHtml(user.phone || 'Not available')}</span>
      </div>
      <div class="detail-box">
        <span class="item-label">Address</span>
        <span class="item-value">${escapeHtml(user.address || 'Not provided')}</span>
      </div>
      <div class="detail-box">
        <span class="item-label">Accounts</span>
        <span class="item-value">${accounts.length}</span>
      </div>
      <div class="detail-box">
        <span class="item-label">Cards</span>
        <span class="item-value">${cards.length}</span>
      </div>
    </div>

    <div class="detail-section">
      <h5>Accounts</h5>
      ${accounts.length ? accounts.map((account) => `
        <div class="admin-card-row">
          <span>${escapeHtml(account.account_type)} · ${escapeHtml(account.account_number)}</span>
          <span>₹${Number(account.balance || 0).toLocaleString()}</span>
          <span class="badge ${account.status === 'ACTIVE' ? 'low' : 'status'}">${escapeHtml(account.status)}</span>
        </div>
      `).join('') : '<div class="info-item"><span class="item-value">No accounts on file.</span></div>'}
    </div>

    <div class="detail-section">
      <h5>Cards &amp; controls</h5>
      ${cards.length ? cards.map((card) => `
        <div class="admin-card-row">
          <span>${escapeHtml(card.card_type)} ending ${escapeHtml(card.last_four)}</span>
          <span class="badge ${card.status === 'ACTIVE' ? 'low' : 'high'}">${escapeHtml(card.status)}</span>
          <div class="case-actions">
            ${card.status !== 'HOLD' ? `<button data-card-id="${card.card_id}" data-card-status="HOLD">Temporary hold</button>` : ''}
            ${card.status !== 'BLOCKED' ? `<button data-card-id="${card.card_id}" data-card-status="BLOCKED">Block</button>` : ''}
            ${card.status !== 'ACTIVE' ? `<button data-card-id="${card.card_id}" data-card-status="ACTIVE">Restore</button>` : ''}
          </div>
        </div>
      `).join('') : '<div class="info-item"><span class="item-value">No cards on file.</span></div>'}
    </div>

    <div class="detail-section">
      <h5>Complete transaction history (${transactions.length})</h5>
      ${transactions.length ? transactions.map((tx) => `
        <div class="mini-row">
          <span>${escapeHtml(tx.merchant || 'Unknown merchant')} · ${escapeHtml(tx.location || 'Location unavailable')}</span>
          <span>${escapeHtml(transactionDirection(tx))} · ${escapeHtml(tx.status)}</span>
          <span>₹${Number(tx.amount || 0).toLocaleString()}</span>
          <span class="badge ${tx.risk_level === 'HIGH' ? 'high' : tx.risk_level === 'MEDIUM' ? 'medium' : 'low'}">${escapeHtml(tx.risk_level || 'LOW')} · ${escapeHtml(tx.transaction_time ? new Date(tx.transaction_time).toLocaleString() : '')}</span>
        </div>
      `).join('') : '<div class="info-item"><span class="item-value">No transactions.</span></div>'}
    </div>

    <div class="detail-section">
      <h5>Phone alert log <span class="small-muted">provider acceptance does not confirm delivery to the handset</span></h5>
      ${sms_messages.length ? sms_messages.map((message) => `
        <div class="mini-row">
          <span>${escapeHtml(message.phone_number || user.phone)}</span>
          <span>${escapeHtml(message.message)}</span>
          <span class="badge status">${escapeHtml(phoneAlertStatus(message.status))} · ${escapeHtml(message.created_at ? new Date(message.created_at).toLocaleString() : '')}</span>
        </div>
      `).join('') : '<div class="info-item"><span class="item-value">No SMS activity recorded.</span></div>'}
    </div>

    <div class="detail-section">
      <h5>Fraud alerts &amp; cases</h5>
      ${alerts.length ? alerts.map((alert) => `<div class="mini-row"><span>${escapeHtml(alert.message)}</span><span class="badge ${alert.risk_level === 'HIGH' ? 'high' : alert.risk_level === 'MEDIUM' ? 'medium' : 'low'}">${escapeHtml(alert.risk_level)}</span><span>${escapeHtml(alert.status)}</span></div>`).join('') : '<div class="info-item"><span class="item-value">No fraud alerts.</span></div>'}
      ${cases.length ? cases.map((caseItem) => `<div class="mini-row"><span>Case #${caseItem.case_id} · ${escapeHtml(caseItem.case_status)}</span><span>${escapeHtml(caseItem.resolution_decision || 'Pending')}</span><span>${caseItem.police_report ? `Police ref ${escapeHtml(caseItem.police_report.reference_number)}` : 'No police report recorded'}</span></div>`).join('') : ''}
    </div>
  `;

  adminCustomerDetail.querySelectorAll('[data-card-status]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await apiRequest(`/api/admin/cards/${button.dataset.cardId}/status`, {
          method: 'PATCH',
          body: JSON.stringify({ status: button.dataset.cardStatus }),
        });
        await loadDashboard();
      } catch (error) {
        alert(error.message);
      }
    });
  });
  renderAdminProfileCases(cases);
}

function renderAdminProfileCases(cases) {
  if (!adminProfileCases) return;
  if (!cases.length) {
    adminProfileCases.innerHTML = '<div class="info-item"><span class="item-value">No fraud cases for this customer.</span></div>';
    return;
  }

  adminProfileCases.innerHTML = cases.map((caseItem) => `
    <div class="profile-case-card">
      <div class="detail-header">
        <strong>Case #${caseItem.case_id} · ${escapeHtml(caseItem.case_status)}</strong>
        <span>${escapeHtml(caseItem.resolution_decision || 'Pending review')}</span>
      </div>
      ${caseItem.police_report ? `<p class="small-muted">Police report recorded · ${escapeHtml(caseItem.police_report.reference_number)} · ${escapeHtml(caseItem.police_report.police_station)}</p>` : ''}
      ${['OPEN', 'INVESTIGATING'].includes(caseItem.case_status) ? `
        <div class="case-actions">
          <button data-profile-case-id="${caseItem.case_id}" data-profile-decision="FRAUD">Confirm fraud &amp; block card</button>
          <button data-profile-case-id="${caseItem.case_id}" data-profile-decision="FALSE_ALARM">Mark false alarm</button>
        </div>
      ` : ''}
      ${caseItem.resolution_decision === 'FRAUD' && !caseItem.police_report ? `<button class="soft-button" data-profile-police-report="${caseItem.case_id}">Record simulated police report</button>` : ''}
      <div class="case-note-form">
        <input data-profile-note="${caseItem.case_id}" placeholder="Add an investigation note" />
        <button class="soft-button" data-profile-note-submit="${caseItem.case_id}">Save note</button>
      </div>
    </div>
  `).join('');

  adminProfileCases.querySelectorAll('[data-profile-decision]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await apiRequest(`/api/cases/${button.dataset.profileCaseId}/resolve`, {
          method: 'POST',
          body: JSON.stringify({ decision: button.dataset.profileDecision }),
        });
        await loadDashboard();
      } catch (error) {
        alert(error.message);
      }
    });
  });

  adminProfileCases.querySelectorAll('[data-profile-police-report]').forEach((button) => {
    button.addEventListener('click', async () => {
      const policeStation = window.prompt('Enter the police station for this simulation record:');
      if (!policeStation?.trim()) return;
      try {
        const response = await apiRequest(`/api/cases/${button.dataset.profilePoliceReport}/police-report`, {
          method: 'POST',
          body: JSON.stringify({ police_station: policeStation.trim() }),
        });
        alert(`${response.message} Reference: ${response.report.reference_number}`);
        await loadDashboard();
      } catch (error) {
        alert(error.message);
      }
    });
  });

  adminProfileCases.querySelectorAll('[data-profile-note-submit]').forEach((button) => {
    button.addEventListener('click', async () => {
      const caseId = button.dataset.profileNoteSubmit;
      const note = adminProfileCases.querySelector(`[data-profile-note="${caseId}"]`)?.value.trim();
      if (!note) {
        alert('Enter an investigation note before saving.');
        return;
      }
      try {
        await apiRequest(`/api/cases/${caseId}/note`, {
          method: 'POST',
          body: JSON.stringify({ note_text: note }),
        });
        await loadDashboard();
      } catch (error) {
        alert(error.message);
      }
    });
  });
}

function renderCases(cases) {
  const isAdmin = state.user?.role === 'BANK_ADMIN';
  if (!cases.length) {
    caseList.innerHTML = `<div class="info-item"><span class="item-value">${isAdmin ? 'No cases in the investigation queue.' : 'No fraud cases for your account.'}</span></div>`;
    return;
  }

  if (!isAdmin) {
    caseList.innerHTML = cases.map((caseItem) => `
      <div class="profile-case-card">
        <div class="detail-header">
          <strong>Case #${caseItem.case_id}</strong>
          <span class="badge ${caseItem.case_status === 'OPEN' || caseItem.case_status === 'INVESTIGATING' ? 'medium' : 'status'}">${escapeHtml(caseItem.case_status)}</span>
        </div>
        ${caseItem.transaction ? `<p>${escapeHtml(caseItem.transaction.merchant || 'Transaction')} · ₹${Number(caseItem.transaction.amount || 0).toLocaleString()}</p>` : ''}
        <span class="small-muted">Decision: ${escapeHtml(caseItem.resolution_decision || 'Pending bank review')}</span>
      </div>
    `).join('');
    return;
  }

  caseList.innerHTML = `
    <div class="case-row header">
      <span>Case</span>
      <span>Customer</span>
      <span>Status</span>
      <span>Action</span>
    </div>
    ${cases.map((caseItem) => `
      <div class="case-row">
        <span>#${caseItem.case_id}</span>
        <span>${escapeHtml(caseItem.customer_name || caseItem.customer_email || `Customer ${caseItem.user_id}`)}</span>
        <span>${escapeHtml(caseItem.case_status)}</span>
        <span class="case-actions">
            ${['OPEN', 'INVESTIGATING'].includes(caseItem.case_status) ? `
              <button data-case-id="${caseItem.case_id}" data-decision="FRAUD">Confirm fraud</button>
              <button data-case-id="${caseItem.case_id}" data-decision="FALSE_ALARM">False alarm</button>
            ` : ''}
            ${caseItem.resolution_decision === 'FRAUD' && !caseItem.police_report && state.user?.role === 'BANK_ADMIN' ? `<button data-police-report="${caseItem.case_id}">Record police report</button>` : ''}
            ${caseItem.police_report ? `<span class="small-muted">Police ref ${escapeHtml(caseItem.police_report.reference_number)}</span>` : ''}
        </span>
      </div>
      <div class="info-item">
        <span class="item-label">Investigation note</span>
        <input data-note-case-id="${caseItem.case_id}" placeholder="Add officer note" />
        <button class="soft-button" data-note-submit="${caseItem.case_id}">Save note</button>
      </div>
    `).join('')}
  `;

  caseList.querySelectorAll('button[data-decision]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await apiRequest(`/api/cases/${button.dataset.caseId}/resolve`, {
          method: 'POST',
          body: JSON.stringify({ decision: button.dataset.decision }),
        });
        loadDashboard();
      } catch (error) {
        alert(error.message);
      }
    });
  });

  caseList.querySelectorAll('[data-police-report]').forEach((button) => {
    button.addEventListener('click', async () => {
      const policeStation = window.prompt('Enter the police station for this simulation record:');
      if (!policeStation?.trim()) return;

      try {
        const response = await apiRequest(`/api/cases/${button.dataset.policeReport}/police-report`, {
          method: 'POST',
          body: JSON.stringify({ police_station: policeStation.trim() }),
        });
        alert(`${response.message} Reference: ${response.report.reference_number}`);
        await loadDashboard();
      } catch (error) {
        alert(error.message);
      }
    });
  });

  caseList.querySelectorAll('[data-note-submit]').forEach((button) => {
    button.addEventListener('click', async () => {
      const caseId = button.dataset.noteSubmit;
      const input = caseList.querySelector(`[data-note-case-id="${caseId}"]`);
      const noteText = input ? input.value.trim() : '';
      if (!noteText) {
        alert('Enter an investigation note before saving.');
        return;
      }

      try {
        await apiRequest(`/api/cases/${caseId}/note`, {
          method: 'POST',
          body: JSON.stringify({ note_text: noteText }),
        });
        loadDashboard();
      } catch (error) {
        alert(error.message);
      }
    });
  });
}

async function createTransaction(event) {
  event.preventDefault();
  const payload = {
    card_id: Number(document.getElementById('transactionCardId').value || 0),
    amount: Number(document.getElementById('transactionAmount').value || 0),
    merchant: document.getElementById('transactionMerchant').value.trim() || 'Velora Market',
    location: document.getElementById('transactionLocation').value.trim() || 'Bengaluru',
    transaction_type: document.getElementById('transactionType').value.trim() || 'online_purchase',
  };

  if (!payload.card_id || payload.amount <= 0) {
    alert('Card ID and amount are required.');
    return;
  }

  try {
    await apiRequest('/api/transactions', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    transactionForm.reset();
    loadDashboard();
  } catch (error) {
    alert(error.message);
  }
}

async function createAccount(event) {
  event.preventDefault();
  const payload = {
    account_number: document.getElementById('accountNumber').value.trim(),
    account_type: document.getElementById('accountType').value.trim() || 'Savings',
    balance: Number(document.getElementById('accountBalance').value || 0),
  };

  try {
    await apiRequest('/api/accounts', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    document.getElementById('accountForm').reset();
    loadDashboard();
  } catch (error) {
    alert(error.message);
  }
}

async function createCard(event) {
  event.preventDefault();
  const firstAccount = accountList.querySelector('[data-account-id]');
  const payload = {
    card_type: document.getElementById('cardType').value.trim(),
    last_four: document.getElementById('cardLastFour').value.trim(),
    expiry_month: document.getElementById('cardMonth').value.trim(),
    expiry_year: document.getElementById('cardYear').value.trim(),
    account_id: firstAccount ? Number(firstAccount.dataset.accountId) : null,
  };

  try {
    await apiRequest('/api/cards', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    document.getElementById('cardForm').reset();
    loadDashboard();
  } catch (error) {
    alert(error.message);
  }
}

document.getElementById('loginForm').addEventListener('submit', handleLogin);
document.getElementById('registerForm').addEventListener('submit', handleRegister);
if (customerMessageForm) {
  customerMessageForm.addEventListener('submit', sendCustomerMessage);
}
if (adminMessageForm) {
  adminMessageForm.addEventListener('submit', sendAdminMessage);
}
if (logoutBtn) {
  logoutBtn.addEventListener('click', () => {
    clearSession();
    renderAuthLayout();
  });
}
if (refreshDataBtn) {
  refreshDataBtn.addEventListener('click', loadDashboard);
}
document.getElementById('backToCustomerDirectory')?.addEventListener('click', () => {
  selectedAdminUserId = null;
  applyRoleView('BANK_ADMIN');
  window.scrollTo({ top: 0, behavior: 'smooth' });
});
if (toggleAccountFormBtn) {
  toggleAccountFormBtn.addEventListener('click', () => accountForm?.classList.toggle('hidden'));
}
if (toggleCardFormBtn) {
  toggleCardFormBtn.addEventListener('click', () => cardForm?.classList.toggle('hidden'));
}
if (accountForm) {
  accountForm.addEventListener('submit', createAccount);
}
if (cardForm) {
  cardForm.addEventListener('submit', createCard);
}
if (transactionForm) {
  transactionForm.addEventListener('submit', createTransaction);
}
if (adminCustomerSearch) {
  adminCustomerSearch.addEventListener('input', () => renderAdminDirectory(currentAdminUsers, currentTransactions));
}
['transactionSearch', 'transactionDirection', 'transactionRisk'].forEach((id) => {
  const filter = document.getElementById(id);
  if (filter) {
    filter.addEventListener(id === 'transactionSearch' ? 'input' : 'change', () => renderTransactions(currentTransactions));
  }
});

restoreSession();
