// ===================== 侧边栏折叠 =====================
const sidebar = document.getElementById('sidebar');
const toggleBtn = document.getElementById('sidebarToggle');
const mainContent = document.getElementById('mainContent');

// 从 localStorage 读取折叠状态
if (sidebar && localStorage.getItem('sidebarCollapsed') === 'true') {
    sidebar.classList.add('collapsed');
}

if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
    });
}

// ===================== CSRF Token =====================
function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
}

// ===================== DOM Ready =====================
document.addEventListener('DOMContentLoaded', function() {
    // Bootstrap Tooltip 初始化
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.forEach(function(el) {
        new bootstrap.Tooltip(el);
    });

    // Bootstrap Popover 初始化
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.forEach(function(el) {
        new bootstrap.Popover(el);
    });

    // 表单验证增强
    var forms = document.querySelectorAll('.needs-validation');
    Array.prototype.slice.call(forms).forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });

    // 通知自动关闭（4秒后淡出）
    var alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            alert.style.opacity = '0';
            alert.style.transition = 'opacity 0.5s';
            setTimeout(function() { alert.remove(); }, 500);
        }, 4000);
    });

    // 数字输入格式化
    var numberInputs = document.querySelectorAll('input[type="number"]');
    numberInputs.forEach(function(input) {
        input.addEventListener('blur', function() {
            if (this.value && !isNaN(this.value)) {
                this.value = parseFloat(this.value).toFixed(2);
            }
        });
    });

    // 日期输入默认填充今天
    var dateInputs = document.querySelectorAll('input[type="date"]:not([value])');
    dateInputs.forEach(function(input) {
        if (!input.value) {
            var today = new Date();
            var dd = String(today.getDate()).padStart(2, '0');
            var mm = String(today.getMonth() + 1).padStart(2, '0');
            var yyyy = today.getFullYear();
            input.value = yyyy + '-' + mm + '-' + dd;
        }
    });

    // 表格行点击跳转
    var tableRows = document.querySelectorAll('.table-clickable tbody tr');
    tableRows.forEach(function(row) {
        row.addEventListener('click', function() {
            var url = this.getAttribute('data-href');
            if (url) {
                window.location = url;
            }
        });
    });

    // 按钮加载状态
    var loadingButtons = document.querySelectorAll('[data-loading-text]');
    loadingButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            var originalText = this.innerHTML;
            var loadingText = this.getAttribute('data-loading-text');
            if (loadingText) {
                this.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>' + loadingText;
                this.disabled = true;
                setTimeout(() => {
                    this.innerHTML = originalText;
                    this.disabled = false;
                }, 3000);
            }
        });
    });
});
