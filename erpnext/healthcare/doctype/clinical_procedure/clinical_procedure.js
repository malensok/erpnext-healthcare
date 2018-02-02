// Copyright (c) 2017, ESS LLP and contributors
// For license information, please see license.txt

frappe.ui.form.on('Clinical Procedure', {
	refresh: function(frm) {
		frm.set_query("patient", function () {
			return {
				filters: {"disabled": 0}
			}
		});
		frm.set_query("appointment", function () {
			return {
				filters: {
					"procedure_template": ["not in", null],
					"status": ['in', 'Open, Scheduled']
				}
			}
		});
		if(frm.doc.maintain_stock){
			frm.set_indicator_formatter('item_code',
				function(doc)	{ return (doc.qty<=doc.actual_qty) ? "green" : "orange" })
		}
		if(!frm.doc.__islocal && frappe.user.has_role("Accounts User")){
			frm.add_custom_button(__("Invoice"), function () {
				frappe.call({
					doc: frm.doc,
					method: "create_invoice",
					callback: function(data){
						if(!data.exc){
							if(data.message.invoice){
								/* frappe.show_alert(__('Sales Invoice {0} created',
								['<a href="#Form/Sales Invoice/'+data.message.invoice+'">' + data.message.invoice+ '</a>'])); */
								frappe.set_route("Form", "Sales Invoice", data.message.invoice);
							}
							cur_frm.reload_doc();
						}
					}
				});
			},"Create")
		}
		if (!frm.doc.complete_procedure && !frm.doc.__islocal && frm.doc.start_procedure){

			if(frm.doc.maintain_stock){
				btn_label = 'Complete and Consume'
				msg = 'Are you sure to Complete and Consume Stock?'
			}else{
				btn_label = 'Complete'
				msg = 'Are you sure to Complete?'
			}

			frm.add_custom_button(__(btn_label), function () {
				frappe.confirm(
				    msg,
				    function(){
							frappe.call({
							 doc: frm.doc,
							 method: "complete",
							 callback: function(r) {
								 if(!r.exc){
									cur_frm.reload_doc();
								 }
							 }
						 });
				    }
				)
			})
		}else if (!frm.doc.start_procedure && !frm.doc.__islocal) {
			frm.add_custom_button(__("Start"), function () {
				frappe.call({
					 doc: frm.doc,
					 method: "start",
					 callback: function(r) {
						 if(!r.exc){
							if(!frm.doc.start_procedure){
								frappe.confirm(
								    "Stock quantity to start procedure is not available in the warehouse. Do you want to record a Stock Transfer",
								    function(){
											frappe.call({
											 doc: frm.doc,
											 method: "make_material_transfer",
											 callback: function(r) {
												 if(!r.exc){
													 	cur_frm.reload_doc();
													 	var doclist = frappe.model.sync(r.message);
 														frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
												 }
											 }
										 });
								    }
								)
							}else{
								cur_frm.reload_doc();
							}
						 }
					 }
				});
			})
		};
		if (frm.doc.__islocal){
			frm.set_df_property("stock_items", "hidden", 1);
			frm.set_df_property("sb_stages", "hidden", 1);
		}else{
			frm.set_df_property("stock_items", "hidden", 0);
			frm.set_df_property("sb_stages", "hidden", 0);
		}
	},
	onload: function(frm){
		if(frm.doc.complete_procedure){
			frm.set_df_property("items", "read_only", 1);
			frm.set_df_property("stages", "read_only", 1);
		}
		if(frm.is_new()) { //TODO: Verify this
			frm.add_fetch("procedure_template", "medical_department", "medical_department")
			frm.set_value("start_tm", null);
		}
	},
	patient: function(frm) {
		if(frm.doc.patient){
			frappe.call({
					"method": "erpnext.healthcare.doctype.patient.patient.get_patient_detail",
					args: {
							patient: frm.doc.patient
					},
					callback: function (data) {
						age = ""
						if(data.message.dob){
							age = calculate_age(data.message.dob)
						}else if (data.message.age){
							age = data.message.age
							if(data.message.age_as_on){
								age = age+" as on "+data.message.age_as_on
							}
						}
						frm.set_value("patient_age", age)
						frm.set_value("patient_sex", data.message.sex)
					}
			})
		}else{
			frm.set_value("patient_age", "")
			frm.set_value("patient_sex", "")
		}
	},
	appointment: function(frm) {
		if(frm.doc.appointment){
			frappe.call({
					"method": "frappe.client.get",
					args: {
							doctype: "Patient Appointment",
							name: frm.doc.appointment
					},
					callback: function (data) {
						frm.set_value("patient", data.message.patient)
						frm.set_value("procedure_template", data.message.procedure_template)
						frm.set_value("medical_department", data.message.department)
						frm.set_value("service_unit", data.message.service_unit)
						frm.set_value("start_dt", data.message.appointment_date)
						frm.set_value("start_tm", data.message.appointment_time)
					}
			})
		}
	},
	procedure_template: function(frm) {
		if(frm.doc.procedure_template){
			frappe.call({
			    "method": "frappe.client.get",
			    args: {
			        doctype: "Clinical Procedure Template",
			        name: frm.doc.procedure_template
			    },
			    callback: function (data) {
						frm.set_value("medical_department", data.message.medical_department)
						frm.set_value("maintain_stock", data.message.maintain_stock)
						frm.set_value("has_stages", data.message.has_stages)
						if(!frm.doc.warehouse){
							frappe.call({
								method: "frappe.client.get_value",
								args: {doctype: "Stock Settings",
											fieldname: "default_warehouse"
											},
								callback: function (data) {
									frm.set_value("warehouse", data.message.default_warehouse)
								}
							});
						}
					}
			})
		}else{
			frm.set_value("maintain_stock", 0)
			frm.set_value("has_stages", 0)
		}
	}
});

cur_frm.set_query("procedure_template", function(doc) {
	return {
		filters: {
			'medical_department': doc.medical_department
		}
	};
});

me.frm.set_query("appointment", function(doc, cdt, cdn) {
	return {
		filters: {
			status:['in',["Open"]]
		}
	};
});

frappe.ui.form.on('Clinical Procedure Item', {
	quantity: function(frm, cdt, cdn){
		var d = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "transfer_qty", d.quantity*d.conversion_factor);
	},
	uom: function(doc, cdt, cdn){
		var d = locals[cdt][cdn];
		if(d.uom && d.item_code){
			return frappe.call({
				method: "erpnext.stock.doctype.stock_entry.stock_entry.get_uom_details",
				args: {
					item_code: d.item_code,
					uom: d.uom,
					qty: d.qty
				},
				callback: function(r) {
					if(r.message) {
						frappe.model.set_value(cdt, cdn, r.message);
					}
				}
			});
		}
	},
	item_code: function(frm, cdt, cdn) {
		var d = locals[cdt][cdn];
		if(d.item_code) {
			args = {
				'item_code'			: d.item_code,
				'transfer_qty'		: d.transfer_qty,
				'company'			: frm.doc.company,
				'quantity'				: d.quantity
			};
			return frappe.call({
				doc: frm.doc,
				method: "get_item_details",
				args: args,
				callback: function(r) {
					if(r.message) {
						var d = locals[cdt][cdn];
						$.each(r.message, function(k, v){
							d[k] = v;
						});
						refresh_field("items");
					}
				}
			});
		}
	}
});

var calculate_age = function(birth) {
  ageMS = Date.parse(Date()) - Date.parse(birth);
  age = new Date();
  age.setTime(ageMS);
  years =  age.getFullYear() - 1970
  return  years + " Year(s) " + age.getMonth() + " Month(s) " + age.getDate() + " Day(s)"
}
