(function () {
  var state = { payload: null, kind: 'bars', run: null, approved: false, campaign: null };
  var $ = function (id) { return document.getElementById(id); };
  function esc(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }
  async function request(url, options) {
    var response = await fetch(url, Object.assign({headers: {'Content-Type': 'application/json'}}, options || {}));
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }
  function setNotice(text) { $('notice').textContent = text || ''; }
  function renderIssues(data) {
    $('issue-count').textContent = data.issues.length + ' 条';
    $('issue-list').innerHTML = data.issues.length ? data.issues.map(function (item) {
      return '<li><span>' + esc(item.line || '-') + '</span><span>' + esc(item.key || '无主键') + '</span><code>' + esc(item.code) + '</code></li>';
    }).join('') : '<li class="empty">暂无异常</li>';
  }
  function renderBreakdown(items) {
    if (!items || !items.length) return '';
    return '<details><summary>' + items.length + ' 项</summary><ul>' + items.map(function (item) {
      return '<li>' + esc(item) + '</li>';
    }).join('') + '</ul></details>';
  }
  function renderRows(data) {
    var labels = Object.assign({label: '记录'}, state.resultColumns);
    var source = data.row_kind === 'source';
    var hasBreakdown = data.rows.some(function (row) { return row.breakdown && row.breakdown.length; });
    var keys = source ? state.inputColumns : Object.keys(labels).filter(function (key) {
      return data.rows.some(function (row) { return Object.hasOwn(row, key); });
    });
    $('row-count').textContent = source ? data.rows.length + ' 行预览' :
      data.summary.PASS + ' 通过 / ' + data.summary.REVIEW + ' 复核 / ' + data.summary.REJECT + ' 阻断';
    var tail = source ? '' : '<th>结论</th>' + (hasBreakdown ? '<th>计算分项</th>' : '');
    $('row-head').innerHTML = '<tr>' + keys.map(function (key) { return '<th>' + esc(labels[key] || key) + '</th>'; }).join('') + tail + '</tr>';
    $('row-body').innerHTML = data.rows.length ? data.rows.map(function (row) {
      var values = keys.map(function (key) { return '<td class="' + (typeof row[key] === 'number' ? 'num' : '') + '">' + esc(row[key]) + '</td>'; }).join('');
      var verdict = source ? '' : '<td><span class="verdict" data-v="' + esc(row.verdict) + '">' + esc(row.verdict || '') + '</span><br><small>' + esc(row.reason || '') + '</small></td>';
      var breakdown = hasBreakdown ? '<td>' + renderBreakdown(row.breakdown) + '</td>' : '';
      return '<tr>' + values + verdict + breakdown + '</tr>';
    }).join('') : '<tr><td class="empty" colspan="' + (keys.length + (source ? 0 : 1)) + '">没有可展示条目</td></tr>';
  }
  function renderLedger(data) {
    if (!data.ledger) { $('ledger-list').innerHTML = '<p class="empty">运行对账后显示</p>'; return; }
    var values = data.ledger;
    $('ledger-list').innerHTML = [
      ['来源行', values.counts.input], ['采信行', values.counts.accepted], ['隔离行', values.counts.isolated],
      ['精确重复', values.counts.duplicates], ['忽略行', values.counts.ignored], ['计算条目', values.counts.computed]
    ].map(function (row) { return '<div class="ledger-row"><span>' + row[0] + '</span><strong>' + row[1] + '</strong></div>'; }).join('') +
      '<div class="ledger-row"><span>' + esc(values.metric_field) + '</span><strong>' + esc(values.metric_total) + '</strong></div>' +
      values.checks.map(function (check) { return '<div class="ledger-row"><span>' + esc(check.label) + '</span><strong class="' + (check.ok ? 'check-ok' : 'check-bad') + '">' + (check.ok ? '通过' : '异常') + '</strong></div>'; }).join('');
  }
  function render(data) {
    state.payload = data;
    $('chart-label').textContent = Object.values(state.resultColumns)[0];
    $('m-input').textContent = data.counts.input;
    $('m-accepted').textContent = data.counts.accepted;
    $('m-isolated').textContent = data.counts.isolated + data.counts.duplicates;
    $('m-rejected').textContent = data.summary.REJECT;
    renderRows(data);
    renderIssues(data);
    renderLedger(data);
    window.renderChart($('chart'), data.chart && data.chart.length ? (state.kind || 'bars') : 'bars', data.chart || []);
  }
  function stageButtons(stages) {
    $('stage-nav').innerHTML = stages.map(function (stage, index) {
      return '<button type="button" data-stage="' + stage.id + '" aria-pressed="' + (index === 0 ? 'true' : 'false') + '">' + esc(stage.name) + '</button>';
    }).join('');
    Array.from(document.querySelectorAll('[data-stage]')).forEach(function (button) {
      button.addEventListener('click', function () {
        document.querySelectorAll('[data-stage]').forEach(function (other) { other.setAttribute('aria-pressed', String(other === button)); });
        loadStage(button.getAttribute('data-stage'));
      });
    });
  }
  async function loadStage(stage) {
    try {
      setNotice('');
      document.body.setAttribute('aria-busy', 'true');
      var payload = await request('/api/stages/' + stage, {method: 'POST', body: JSON.stringify({profile: $('profile').value})});
      render(payload);
    } catch (error) { setNotice(error.message); }
    finally { document.body.removeAttribute('aria-busy'); }
  }
  async function runBatch() {
    try {
      setNotice('');
      $('run').disabled = true;
      var run = await request('/api/runs', {method: 'POST', body: JSON.stringify({profile: $('profile').value})});
      state.run = run;
      state.approved = run.status === 'APPROVED';
      render(run);
      $('run-status').textContent = run.status + ' · rev ' + run.revision;
      $('revision').textContent = 'rev ' + run.revision;
      $('sign').disabled = run.summary.REJECT > 0 || state.approved;
      $('hold').disabled = state.approved;
      $('download').hidden = !state.approved;
      if (state.approved) $('download').href = '/api/runs/' + run.run_id + '/evidence';
    } catch (error) { setNotice(error.message); }
    finally { $('run').disabled = false; }
  }
  async function review(decision) {
    if (!state.run) return;
    try {
      var run = await request('/api/runs/' + state.run.run_id + '/review', {
        method: 'POST',
        body: JSON.stringify({decision: decision, comment: $('comment').value, expected_revision: state.run.revision})
      });
      state.run = run;
      state.approved = run.status === 'APPROVED';
      $('run-status').textContent = run.status + ' · rev ' + run.revision;
      $('revision').textContent = 'rev ' + run.revision;
      $('sign').disabled = true;
      $('hold').disabled = true;
      $('download').hidden = !state.approved;
      if (state.approved) $('download').href = '/api/runs/' + run.run_id + '/evidence';
    } catch (error) { setNotice(error.message); }
  }
  var LABELS = {DRAFT: '已占额度', ISSUED: '已签发', WAITLIST: '候补', EXCLUDED: '不占额度', CANCELLED: '已取消'};
  var REASONS = {PROMISED: '承诺兑现', PROMISED_PREEMPTED: '承诺兑现（额度已被更早订单挤占）', NOT_ISSUED: '待签发', QUOTA_INSUFFICIENT: '额度不足', COUPON_CAUSES_LOSS: '用券后亏损', CANCELLED: '已取消'};
  function renderQuota(data) {
    if (!data) { $('quota-usage').innerHTML = '<p class="empty">尚无活动</p>'; $('quota-orders').innerHTML = ''; return; }
    state.campaign = data.id;
    var usage = data.usage;
    $('quota-hint').textContent = data.name + ' · 额度 ' + usage.quota_cents + ' 分';
    $('quota-usage').innerHTML = [
      ['活动额度', usage.quota_cents], ['已占额度', usage.reserved_cents], ['剩余额度', usage.available_cents],
      ['已签发承诺', usage.committed_cents], ['被挤占承诺', usage.preempted_cents],
      ['敞口合计', usage.exposure_cents], ['超发', usage.overcommitted_cents]
    ].map(function (row) {
      return '<div class="ledger-row"><span>' + row[0] + '</span><strong class="' +
        (row[0] === '超发' && row[1] > 0 ? 'check-bad' : '') + '">' + row[1] + '</strong></div>';
    }).join('');
    $('quota-orders').innerHTML = data.orders.length ? data.orders.map(function (item) {
      var actions = '';
      if (item.can_issue) actions += '<button type="button" data-issue="' + esc(item.order_id) + '">签发</button> ';
      if (item.state !== 'CANCELLED') actions += '<button type="button" data-cancel="' + esc(item.order_id) + '">取消</button>';
      return '<tr><td>' + esc(item.order_id) + '</td><td>' + esc(item.received_at) + '</td><td class="num">' + item.coupon_cents +
        '</td><td class="num">' + item.margin_with_coupon + '</td><td><span class="verdict" data-v="' +
        (item.can_ship ? 'PASS' : item.status === 'WAITLIST' || item.status === 'EXCLUDED' ? 'REJECT' : 'REVIEW') + '">' +
        esc(LABELS[item.status] || item.status) + '</span></td><td><small>' + esc(REASONS[item.reason] || item.reason) +
        (item.waitlist_position ? '（第 ' + item.waitlist_position + ' 位）' : '') + '</small></td><td>' +
        (item.can_ship ? '可发货' : '不可发货') + '</td><td>' + actions + '</td></tr>';
    }).join('') : '<tr><td class="empty" colspan="8">尚无订单</td></tr>';
    Array.from(document.querySelectorAll('[data-issue]')).forEach(function (button) {
      button.addEventListener('click', function () { quotaAction(button.getAttribute('data-issue'), 'issue'); });
    });
    Array.from(document.querySelectorAll('[data-cancel]')).forEach(function (button) {
      button.addEventListener('click', function () { quotaAction(button.getAttribute('data-cancel'), 'cancel'); });
    });
  }
  async function quotaAction(orderId, action) {
    if (!state.campaign) return;
    try {
      var result = await request('/api/campaigns/' + state.campaign + '/orders/' + encodeURIComponent(orderId) + '/' + action, {method: 'POST'});
      renderQuota(result.campaign);
    } catch (error) { setNotice(error.message); }
  }
  async function createCampaign() {
    try {
      var result = await request('/api/campaigns', {method: 'POST', body: JSON.stringify({
        name: $('quota-name').value, quota_cents: Number($('quota-amount').value || 0)
      })});
      await refreshCampaigns();
      renderQuota(result);
    } catch (error) { setNotice(error.message); }
  }
  async function submitOrder() {
    if (!state.campaign) { setNotice('请先创建或选择活动'); return; }
    try {
      var result = await request('/api/campaigns/' + state.campaign + '/orders', {method: 'POST', body: JSON.stringify({
        order_id: $('q-id').value, received_at: $('q-time').value, line_qty: Number($('q-qty').value || 0),
        sell_price_cents: Number($('q-sell').value || 0), unit_cost_cents: Number($('q-cost').value || 0),
        supplier_fund_cents: Number($('q-fund').value || 0), coupon_cents: Number($('q-coupon').value || 0)
      })});
      renderQuota(result.campaign);
    } catch (error) { setNotice(error.message); }
  }
  async function refreshCampaigns() {
    var data = await request('/api/campaigns');
    $('quota-campaign').innerHTML = '<option value="">新建活动</option>' + data.campaigns.map(function (item) {
      return '<option value="' + esc(item.id) + '">' + esc(item.name) + ' · ' + item.usage.available_cents + '/' + item.quota_cents + '</option>';
    }).join('');
    if (state.campaign) $('quota-campaign').value = state.campaign;
  }
  async function loadCampaign(campaignId) {
    if (!campaignId) return;
    try { renderQuota(await request('/api/campaigns/' + campaignId)); }
    catch (error) { setNotice(error.message); }
  }
  async function boot() {
    try {
      var catalog = await request('/api/catalog');
      state.kind = catalog.chart;
      state.resultColumns = catalog.result_columns;
      state.inputColumns = catalog.columns;
      stageButtons(catalog.stages.slice(0, 5));
      document.querySelector('.rail-note').textContent = catalog.code + ' · ' + catalog.stages[6].name;
      await loadStage('intake');
    } catch (error) { setNotice(error.message); }
    $('run').addEventListener('click', runBatch);
    $('quota-create').addEventListener('click', createCampaign);
    $('q-submit').addEventListener('click', submitOrder);
    $('quota-campaign').addEventListener('change', function () { loadCampaign($('quota-campaign').value); });
    try { await refreshCampaigns(); } catch (error) { setNotice(error.message); }
    $('sign').addEventListener('click', function () { review('APPROVED'); });
    $('hold').addEventListener('click', function () { review('HELD'); });
    $('profile').addEventListener('change', function () {
      state.run = null; state.approved = false;
      $('sign').disabled = true; $('hold').disabled = true; $('download').hidden = true;
      $('run-status').textContent = '未执行批次'; $('revision').textContent = 'rev 0';
      loadStage('intake');
    });
  }
  document.addEventListener('DOMContentLoaded', boot);
})();
