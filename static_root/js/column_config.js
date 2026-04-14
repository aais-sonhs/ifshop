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
            '.cc-dropdown{position:relative !important;display:inline-flex !important;align-items:center !important;}' +
            '.cc-trigger.btn{display:inline-flex !important;align-items:center !important;gap:6px !important;border-radius:999px !important;border:1px solid #cbd5e1 !important;background:#fff !important;color:#334155 !important;font-weight:600 !important;box-shadow:0 1px 2px rgba(15,23,42,0.04) !important;}' +
            '.cc-trigger.btn:hover,.cc-trigger.btn:focus,.show>.cc-trigger.btn.dropdown-toggle{background:#eff6ff !important;border-color:#93c5fd !important;color:#1d4ed8 !important;box-shadow:0 0 0 0.2rem rgba(59,130,246,0.12) !important;}' +
            '.cc-menu.dropdown-menu{min-width:260px !important;max-width:320px !important;max-height:420px !important;overflow-y:auto !important;padding:0 !important;border:1px solid #dbe3eb !important;border-radius:14px !important;background:#fff !important;background-color:#fff !important;box-shadow:0 18px 36px rgba(15,23,42,0.16) !important;}' +
            '.cc-header{display:block !important;padding:12px 14px !important;border-bottom:1px solid #e2e8f0 !important;background:linear-gradient(180deg,#f8fbff 0%,#eef6ff 100%) !important;}' +
            '.cc-title{display:flex !important;align-items:center !important;gap:8px !important;font-size:12px !important;font-weight:700 !important;letter-spacing:0.04em !important;text-transform:uppercase !important;color:#1e3a8a !important;}' +
            '.cc-title span,.cc-title i{color:#1e3a8a !important;}' +
            '.cc-subtitle{margin-top:4px !important;font-size:12px !important;color:#64748b !important;line-height:1.45 !important;}' +
            '.cc-body{display:block !important;padding:8px 0 !important;background:#fff !important;background-color:#fff !important;}' +
            '.cc-toggle-item{display:flex !important;align-items:flex-start !important;gap:10px !important;width:100% !important;padding:8px 14px !important;margin:0 !important;color:#1f2937 !important;font-size:13px !important;line-height:1.4 !important;white-space:normal !important;word-break:break-word !important;background:#fff !important;background-color:#fff !important;border:0 !important;cursor:pointer !important;text-decoration:none !important;}' +
            '.cc-toggle-item:hover,.cc-toggle-item:focus{background:#f8fafc !important;background-color:#f8fafc !important;color:#0f172a !important;}' +
            '.cc-toggle-item input{width:16px !important;height:16px !important;margin-top:2px !important;flex:0 0 auto !important;accent-color:#1565c0;}' +
            '.cc-toggle-item span{flex:1 1 auto !important;min-width:0 !important;color:#1f2937 !important;}' +
            '.cc-footer{display:flex !important;gap:8px !important;padding:10px 14px !important;border-top:1px solid #e2e8f0 !important;background:#f8fafc !important;background-color:#f8fafc !important;position:sticky !important;bottom:0 !important;}' +
            '.cc-footer .btn{flex:1 1 0 !important;border-radius:10px !important;font-size:12px !important;font-weight:600 !important;padding:6px 10px !important;white-space:nowrap !important;}' +
            '.cc-footer .cc-select-all{border:1px solid #93c5fd !important;background:#fff !important;color:#1d4ed8 !important;}' +
            '.cc-footer .cc-select-all:hover,.cc-footer .cc-select-all:focus{border-color:#60a5fa !important;background:#dbeafe !important;color:#1e40af !important;}' +
            '.cc-footer .cc-reset{border:1px solid #cbd5e1 !important;background:#fff !important;color:#334155 !important;}' +
            '.cc-footer .cc-reset:hover,.cc-footer .cc-reset:focus{border-color:#94a3b8 !important;background:#f1f5f9 !important;color:#0f172a !important;}' +
            '.cc-empty{padding:12px 14px !important;font-size:13px !important;color:#64748b !important;background:#fff !important;}' +
            '@media (max-width: 576px){.cc-menu.dropdown-menu{min-width:240px !important;max-width:min(92vw,320px) !important;}}';

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
            itemsHtml += '<label class="cc-toggle-item">' +
                '<input type="checkbox" class="cc-col-toggle" data-col="'+col.key+'" '+checked+'> ' +
                '<span>'+col.label+'</span></label>';
        });

        if(!itemsHtml){
            itemsHtml = '<div class="cc-empty">Tat ca cot tren bang nay dang luon hien thi.</div>';
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
