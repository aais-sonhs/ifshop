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

        // Load saved state
        this.state = this._loadState();

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

    ColumnConfig.prototype._renderButton = function(){
        var self = this;
        var $container = $(this.buttonContainer);
        if(!$container.length) return;

        // Build dropdown items
        var itemsHtml = '';
        this.columns.forEach(function(col){
            if(col.alwaysOn) return; // Don't show toggle for always-on cols
            var checked = self.isVisible(col.key) ? 'checked' : '';
            itemsHtml += '<label class="dropdown-item cc-toggle-item" style="cursor:pointer;display:flex;align-items:center;gap:8px;padding:6px 16px;margin:0;font-size:13px;">' +
                '<input type="checkbox" class="cc-col-toggle" data-col="'+col.key+'" '+checked+' style="accent-color:#1565c0;width:16px;height:16px;"> ' +
                '<span>'+col.label+'</span></label>';
        });

        var html = '<div class="dropdown d-inline-block">' +
            '<button class="btn btn-sm btn-outline-secondary dropdown-toggle" data-toggle="dropdown" title="Tùy chỉnh cột hiển thị" id="btn_col_config">' +
            '<i class="fas fa-columns mr-1"></i>Cột</button>' +
            '<div class="dropdown-menu dropdown-menu-right shadow" style="min-width:220px;max-height:400px;overflow-y:auto;padding:8px 0;" id="cc_dropdown">' +
            '<div style="padding:6px 16px;border-bottom:1px solid #eee;margin-bottom:4px;">' +
            '<strong style="font-size:12px;color:#666;text-transform:uppercase;"><i class="fas fa-eye mr-1"></i>Hiển thị cột</strong></div>' +
            itemsHtml +
            '<div class="dropdown-divider"></div>' +
            '<div style="padding:4px 16px;display:flex;gap:8px;">' +
            '<button class="btn btn-xs btn-outline-primary cc-select-all" style="flex:1;">Chọn tất cả</button>' +
            '<button class="btn btn-xs btn-outline-secondary cc-reset" style="flex:1;">Mặc định</button></div>' +
            '</div></div>';

        $container.prepend(html);

        // Prevent dropdown close on click inside
        $(document).on('click', '#cc_dropdown', function(e){
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
