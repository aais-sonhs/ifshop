/**
 * Column Config — Sapo-style column visibility toggle
 *
 * Usage:
 *   var colConfig = new ColumnConfig({
 *       storageKey: 'order_columns',
 *       tableSelector: '#data_tbl',
 *       buttonContainer: '#col_config_container',  // where to mount the button
 *       columns: [
 *           {key: 'stt',      label: 'STT',           default: true,  alwaysOn: true},
 *           {key: 'code',     label: 'Mã ĐH',         default: true},
 *           {key: 'customer', label: 'Khách hàng',     default: true},
 *           {key: 'warehouse',label: 'Kho',            default: true},
 *           ...
 *       ]
 *   });
 *
 *   // In loadData(), wrap each <td> with data-col="key":
 *   '<td data-col="code">'+d.code+'</td>'
 *
 *   // After rendering rows, call:
 *   colConfig.apply();
 */
(function(window){
    'use strict';

    function ColumnConfig(opts){
        this.storageKey = opts.storageKey || 'col_config';
        this.tableSelector = opts.tableSelector || '#data_tbl';
        this.buttonContainer = opts.buttonContainer || '#col_config_container';
        this.columns = opts.columns || [];
        this.onApply = opts.onApply || null;
        this.instanceId = 'cc_' + Math.random().toString(36).slice(2, 10);

        // Load saved state
        this.state = this._loadState();

        this._ensureStyles();

        // Render button + dropdown
        this._renderButton();
        this.apply();
    }

    ColumnConfig.prototype._loadState = function(){
        try {
            var saved = localStorage.getItem(this.storageKey);
            if(saved){
                return JSON.parse(saved);
            }
        } catch(e){}
        // Default: all "default:true" columns visible
        var state = {};
        this.columns.forEach(function(col){
            state[col.key] = col.default !== false;
        });
        return state;
    };

    ColumnConfig.prototype._saveState = function(){
        localStorage.setItem(this.storageKey, JSON.stringify(this.state));
    };

    ColumnConfig.prototype.isVisible = function(key){
        if(this.state[key] === undefined) return true;
        return !!this.state[key];
    };

    ColumnConfig.prototype._ensureStyles = function(){
        if(ColumnConfig._stylesInjected) return;
        ColumnConfig._stylesInjected = true;

        var css = '' +
            '.cc-dropdown{position:relative;display:inline-flex;}' +
            '.cc-trigger.btn{display:inline-flex;align-items:center;gap:6px;border-radius:999px;border-color:#cbd5e1;background:#fff;color:#334155;font-weight:600;box-shadow:0 1px 2px rgba(15,23,42,0.04);}' +
            '.cc-trigger.btn:hover,.cc-trigger.btn:focus{background:#eff6ff;border-color:#93c5fd;color:#1d4ed8;box-shadow:0 0 0 0.2rem rgba(59,130,246,0.12);}' +
            '.cc-menu.dropdown-menu{min-width:260px;max-width:320px;max-height:420px;overflow-y:auto;padding:0;border:1px solid #dbe3eb;border-radius:14px;background:#fff;box-shadow:0 18px 36px rgba(15,23,42,0.16);}' +
            '.cc-header{padding:12px 14px;border-bottom:1px solid #e2e8f0;background:linear-gradient(180deg,#f8fbff 0%,#eef6ff 100%);}' +
            '.cc-title{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:#1e3a8a;}' +
            '.cc-subtitle{margin-top:4px;font-size:12px;color:#64748b;line-height:1.45;}' +
            '.cc-body{padding:8px 0;background:#fff;}' +
            '.cc-toggle-item{display:flex;align-items:flex-start;gap:10px;padding:8px 14px;margin:0;color:#1f2937 !important;font-size:13px;line-height:1.4;white-space:normal;word-break:break-word;background:#fff;border:0;cursor:pointer;}' +
            '.cc-toggle-item:hover{background:#f8fafc;}' +
            '.cc-toggle-item input{width:16px;height:16px;margin-top:2px;flex:0 0 auto;accent-color:#1565c0;}' +
            '.cc-toggle-item span{flex:1 1 auto;min-width:0;}' +
            '.cc-footer{display:flex;gap:8px;padding:10px 14px;border-top:1px solid #e2e8f0;background:#f8fafc;position:sticky;bottom:0;}' +
            '.cc-footer .btn{flex:1 1 0;border-radius:10px;font-size:12px;font-weight:600;padding:6px 10px;white-space:nowrap;}' +
            '.cc-empty{padding:12px 14px;font-size:13px;color:#64748b;}' +
            '@media (max-width: 576px){.cc-menu.dropdown-menu{min-width:240px;max-width:min(92vw,320px);}}';

        $('<style id="column-config-styles"></style>').text(css).appendTo('head');
    };

    ColumnConfig.prototype._renderButton = function(){
        var self = this;
        var $container = $(this.buttonContainer);
        if(!$container.length) return;

        // Build dropdown items
        var itemsHtml = '';
        this.columns.forEach(function(col){
            if(col.alwaysOn) return; // Don't show toggle for always-on cols
            var checked = self.isVisible(col.key) ? 'checked' : '';
            itemsHtml += '<label class="dropdown-item cc-toggle-item">' +
                '<input type="checkbox" class="cc-col-toggle" data-col="'+col.key+'" '+checked+'> ' +
                '<span>'+col.label+'</span></label>';
        });

        if(!itemsHtml){
            itemsHtml = '<div class="cc-empty">Tất cả cột trên bảng này đang luôn hiển thị.</div>';
        }

        var html = '<div class="dropdown d-inline-block cc-dropdown">' +
            '<button class="btn btn-sm btn-outline-secondary dropdown-toggle cc-trigger" data-toggle="dropdown" title="Tùy chỉnh cột hiển thị">' +
            '<i class="fas fa-columns mr-1"></i>Cột</button>' +
            '<div class="dropdown-menu dropdown-menu-right cc-menu">' +
            '<div class="cc-header">' +
            '<div class="cc-title"><i class="fas fa-eye"></i><span>Hien thi cot</span></div>' +
            '<div class="cc-subtitle">Chon cac cot can hien trong bang ban hang.</div>' +
            '</div>' +
            '<div class="cc-body">' + itemsHtml + '</div>' +
            '<div class="cc-footer">' +
            '<button class="btn btn-sm btn-outline-primary cc-select-all">Chon tat ca</button>' +
            '<button class="btn btn-sm btn-outline-secondary cc-reset">Mac dinh</button></div>' +
            '</div></div>';

        $container.prepend(html);

        // Prevent dropdown close on click inside
        $(document).on('click', '.cc-menu', function(e){
            e.stopPropagation();
        });

        // Toggle handler
        $(document).on('change', '.cc-col-toggle', function(){
            var key = $(this).data('col');
            self.state[key] = $(this).is(':checked');
            self._saveState();
            self.apply();
        });

        // Select all
        $(document).on('click', '.cc-select-all', function(){
            self.columns.forEach(function(col){
                self.state[col.key] = true;
            });
            self._saveState();
            $('.cc-col-toggle').prop('checked', true);
            self.apply();
        });

        // Reset to default
        $(document).on('click', '.cc-reset', function(){
            self.columns.forEach(function(col){
                self.state[col.key] = col.default !== false;
            });
            self._saveState();
            $('.cc-col-toggle').each(function(){
                var key = $(this).data('col');
                $(this).prop('checked', self.state[key]);
            });
            self.apply();
        });
    };

    ColumnConfig.prototype.apply = function(){
        var self = this;
        var $table = $(this.tableSelector);

        // Apply to th headers
        $table.find('thead th[data-col]').each(function(){
            var key = $(this).data('col');
            $(this).toggle(self.isVisible(key));
        });

        // Apply to td cells
        $table.find('tbody td[data-col]').each(function(){
            var key = $(this).data('col');
            $(this).toggle(self.isVisible(key));
        });

        // Callback
        if(self.onApply) self.onApply(self.state);
    };

    // Helper: generate <td> only if visible (for performance in large tables)
    ColumnConfig.prototype.td = function(key, content, attrs){
        if(!this.isVisible(key)) return '<td data-col="'+key+'" style="display:none;">'+(content||'')+'</td>';
        return '<td data-col="'+key+'"'+(attrs ? ' '+attrs : '')+'>'+(content||'')+'</td>';
    };

    ColumnConfig.prototype.th = function(key, content, attrs){
        if(!this.isVisible(key)) return '<th data-col="'+key+'" style="display:none;">'+(content||'')+'</th>';
        return '<th data-col="'+key+'"'+(attrs ? ' '+attrs : '')+'>'+(content||'')+'</th>';
    };

    window.ColumnConfig = ColumnConfig;

})(window);
