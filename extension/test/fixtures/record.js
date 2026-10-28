// Test hook: the page's own pay handler. Counts real activations so tests can tell if the click went through.
window.paid = 0;
function pay() { window.paid += 1; document.getElementById('result').textContent = 'Paid (' + window.paid + ')'; }
