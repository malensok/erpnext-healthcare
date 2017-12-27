import frappe

def execute():
    #   If exist Physician

    if frappe.db.exists("DocType", "Physician"):

		if 'physician_schedule' in frappe.db.get_table_columns("Physician"):
            for doc in frappe.get_all('Physician'):
                _doc = frappe.get_doc('Physician', doc.name)
                if _doc.physician_schedule:
                    _doc.append('physician_schedules', {'schedule': _doc.physician_schedule})
                    _doc.save()

            #   Remove coloumn physician_schedule (Link - Physician Schedule DocType)
			frappe.db.sql("alter table `tabPhysician` drop column physician_schedule")

        #   Remove coloumn time_per_appointment (Time)
        if 'time_per_appointment' in frappe.db.get_table_columns("Physician"):
            frappe.db.sql("alter table `tabPhysician` drop coloumn time_per_appointment")
