frappe.pages['engineering-and-production-reports'].on_page_load = function(wrapper) {
    wrapper.epr = new EngineeringProductionReports(wrapper);
};

class EngineeringProductionReports {
    constructor(wrapper) {
        this.page = frappe.ui.make_app_page({parent:wrapper, title:__('Engineering and Production Reports'), single_column:true});
        this.main = this.page.main.addClass('epr-page');
        this.method = 'engineering.engineering.page.engineering_and_production_reports.engineering_and_production_reports.';
        this.types = []; this.rows = []; this.sequence = 0; this.viewSequence = 0;
        this.main.html(`<div class="epr-saved-panel">
            <div class="epr-filters"></div><div class="epr-selector"></div>
            <div class="epr-actions">
                <button type="button" class="btn btn-default epr-clear">${__('Clear Selection')}</button>
                <button type="button" class="btn btn-default epr-refresh">${__('Refresh')}</button>
                <button type="button" class="btn btn-primary epr-download" disabled>${__('Download Report')}</button>
            </div><div class="epr-message" role="status" aria-live="polite"></div>
            <section class="epr-preview hide">
                <div class="epr-preview-title"></div><div class="epr-preview-meta"></div>
                <iframe title="${__('Saved report preview')}" sandbox=""></iframe>
            </section></div>`);
        this.controls = {};
        const add = (name, label, fieldtype, options, required=false) => {
            const parent=$('<div>').appendTo(this.main.find(name==='saved_report'?'.epr-selector':'.epr-filters'));
            this.controls[name]=frappe.ui.form.make_control({parent,render_input:true,
                df:{fieldname:name,label:__(label),fieldtype,options,reqd:required,change:()=>this.changed(name)}});
        };
        add('department','Department','Select','');
        add('report_type','Report Type','Select','');
        add('site','Site','Link','Location',true);
        add('report_date','Report Date','Date',null,true);
        add('saved_report','Saved Report','Select','');
        this.main.on('click','.epr-clear',()=>this.clearSelection());
        this.main.on('click','.epr-refresh',()=>this.load());
        this.main.on('click','.epr-download',()=>this.download());
        this.init();
    }
    escape(value) {return frappe.utils.escape_html(String(value ?? ''));}
    message(value) {this.main.find('.epr-message').text(value);}
    selected() {return this.types.find(type=>type.key===this.controls.report_type.get_value());}
    async init() {
        try {
            this.types=(await frappe.call({method:this.method+'get_report_types'})).message || [];
            this.setting=true;
            await this.resetSelector();
            if (!this.types.length) {this.message(__('No saved report types are available with your permissions.'));return;}
            const departments=[...new Set(this.types.map(type=>type.department))];
            this.controls.department.df.options=departments.join('\n');
            this.controls.department.refresh();
            await this.controls.department.set_value(departments[0]);
            await this.updateTypes();
            this.message(__('Select a site and report date to find saved reports.'));
        } catch(error) {
            this.message(__('Could not load report types. Please refresh the page.'));
        } finally {this.setting=false;}
    }
    async updateTypes() {
        const types=this.types.filter(type=>type.department===this.controls.department.get_value());
        this.controls.report_type.df.options=types.map(type=>({label:__(type.label),value:type.key}));
        this.controls.report_type.refresh();
        await this.controls.report_type.set_value(types[0]?.key || '');
    }
    async changed(name) {
        if (this.setting || !this.types.length) return;
        if (name==='saved_report') {
            await this.view(this.controls.saved_report.get_value());
            return;
        }
        // Invalidate outstanding searches/previews before awaiting control updates.
        this.sequence++;
        this.closePreview();
        this.setting=true;
        try {
            await this.resetSelector();
            if (name==='department') await this.updateTypes();
        } finally {this.setting=false;}
        await this.load();
    }
    filters() {
        const type=this.selected(), site=this.controls.site.get_value(), report_date=this.controls.report_date.get_value();
        return type && site && report_date ? {report_type:type.key,site,report_date} : null;
    }
    closePreview() {
        this.viewSequence++;
        this.viewed=null;
        this.main.find('.epr-download').prop('disabled',true);
        this.main.find('.epr-preview').addClass('hide');
        this.main.find('iframe').attr('srcdoc','');
    }
    async resetSelector() {
        this.rows=[];
        this.controls.saved_report.df.options=[{value:'',label:__('Select a saved report…')}];
        this.controls.saved_report.df.read_only=1;
        this.controls.saved_report.refresh();
        this.closePreview();
        await this.controls.saved_report.set_value('');
    }
    async clearSelection() {
        this.closePreview();
        this.setting=true;
        try {await this.controls.saved_report.set_value('');}
        finally {this.setting=false;}
        this.message(this.rows.length ? __('Select a saved report to view it.') : __('Select a site and report date to find saved reports.'));
    }
    reportLabel(row, type=this.selected()) {
        let period='Full Daily';
        if (type.filters.includes('hour_slot')) {
            period=String(row.hour_slot || '').replace(/\b(\d{1,2}):00/g,(_,hour)=>`${hour.padStart(2,'0')}:00`).replace(/\s*-\s*/g,'-');
        } else if (['Day','Day Shift'].includes(row.shift)) period='Day Shift';
        else if (['Night','Night Shift'].includes(row.shift)) period='Night Shift';
        return [String(row.report_date || '').slice(0,10),row.site,period].join(' | ');
    }
    async load() {
        const sequence=++this.sequence, args=this.filters();
        this.setting=true;
        try {await this.resetSelector();}
        finally {this.setting=false;}
        if (!args) {
            this.main.find('.epr-refresh').prop('disabled',false);
            this.message(__('Select a site and report date to find saved reports.'));
            return;
        }
        this.main.find('.epr-refresh').prop('disabled',true);
        this.message(__('Loading saved reports…'));
        try {
            const rows=new Map(), cursors=new Set();
            let start=0;
            // Reuse the existing permission/eligibility-aware search; paging is transport only.
            do {
                if (cursors.has(start)) throw new Error('Non-advancing saved-report cursor');
                cursors.add(start);
                const result=(await frappe.call({method:this.method+'search_reports',args:{...args,start}})).message;
                if (sequence!==this.sequence) return;
                for (const row of result.rows) rows.set(row.name,row);
                start=result.next_start;
            } while (start!==null && start!==undefined);
            this.rows=[...rows.values()];
            this.controls.saved_report.df.options=[{value:'',label:__('Select a saved report…')},
                ...this.rows.map(row=>({value:row.name,label:this.escape(this.reportLabel(row))}))];
            this.controls.saved_report.df.read_only=this.rows.length?0:1;
            this.controls.saved_report.refresh();
            this.message(this.rows.length ? __('{0} saved reports. Select one to view it.',[this.rows.length]) : __('No saved reports match this site and report date.'));
        } catch(error) {
            if (sequence===this.sequence) this.message(__('Could not load saved reports. Click Refresh to retry.'));
        } finally {
            if (sequence===this.sequence) this.main.find('.epr-refresh').prop('disabled',false);
        }
    }
    async view(name) {
        this.closePreview();
        if (!name) {this.message(__('Select a saved report to view it.'));return;}
        const row=this.rows.find(row=>row.name===name), type=this.selected();
        if (!row || !type) return;
        const sequence=this.viewSequence;
        this.message(__('Loading saved report…'));
        try {
            const response=await frappe.call({method:this.method+'view_report',args:{report_type:type.key,name}});
            if (sequence!==this.viewSequence || this.controls.saved_report.get_value()!==name) return;
            this.viewed={...row,report_type:type.key};
            this.main.find('.epr-preview-title').text(__(type.label));
            this.main.find('.epr-preview-meta').text(this.reportLabel(row,type));
            this.main.find('iframe').attr('srcdoc',response.message.html);
            this.main.find('.epr-preview').removeClass('hide');
            this.main.find('.epr-download').prop('disabled',false);
            this.message('');
        } catch(error) {
            if (sequence===this.viewSequence) this.message(__('This saved report could not be opened. Check your access or click Refresh to retry.'));
        }
    }
    download() {
        if (!this.viewed) return;
        const query=new URLSearchParams({report_type:this.viewed.report_type,name:this.viewed.name});
        window.open(`/api/method/${this.method}download_pdf?${query}`,'_blank','noopener');
    }
}
