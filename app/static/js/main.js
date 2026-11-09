/**
 * AttendSync Client Scripting & Interactive Utilities
 * Supports table filtering, quick bulk attendance toggling, and CSV export.
 */

// Filter table rows by search keyword input
function filterTable(inputId, tableId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const filter = input.value.toLowerCase().trim();
    const table = document.getElementById(tableId);
    if (!table) return;
    const rows = table.getElementsByTagName("tbody")[0].getElementsByTagName("tr");

    let visibleCount = 0;
    for (let i = 0; i < rows.length; i++) {
        const text = rows[i].textContent.toLowerCase();
        if (text.includes(filter)) {
            rows[i].style.display = "";
            visibleCount++;
        } else {
            rows[i].style.display = "none";
        }
    }

    const countBadge = document.getElementById("filterMatchCount");
    if (countBadge) {
        countBadge.textContent = `${visibleCount} visible`;
    }
}

// Bulk toggle attendance statuses
function setAllAttendance(targetStatus) {
    if (targetStatus === "Present") {
        document.querySelectorAll(".attendance-radio-present").forEach((radio) => {
            radio.checked = true;
        });
    } else if (targetStatus === "Absent") {
        document.querySelectorAll(".attendance-radio-absent").forEach((radio) => {
            radio.checked = true;
        });
    }
}

// Client-side CSV Exporter for Roster and Summary Tables
function exportTableToCSV(tableId, filename = "attendsync_report.csv") {
    const table = document.getElementById(tableId);
    if (!table) return;

    let csv = [];
    const rows = table.querySelectorAll("tr");

    for (let i = 0; i < rows.length; i++) {
        // Skip hidden rows if any
        if (rows[i].style.display === "none") continue;

        let row = [];
        const cols = rows[i].querySelectorAll("th, td");

        for (let j = 0; j < cols.length; j++) {
            // Strip out action buttons, radio groups, and extra whitespace
            let data = cols[j].innerText.replace(/(\r\n|\n|\r)/gm, " ").trim();
            // Escape double quotes
            data = data.replace(/"/g, '""');
            row.push('"' + data + '"');
        }
        csv.push(row.join(","));
    }

    // Trigger download
    const csvFile = new Blob([csv.join("\n")], { type: "text/csv;charset=utf-8;" });
    const downloadLink = document.createElement("a");
    downloadLink.download = filename;
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = "none";
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
}

document.addEventListener("DOMContentLoaded", () => {
    // Auto-dismiss alerts after 6 seconds
    setTimeout(() => {
        document.querySelectorAll(".flash-messages .alert").forEach((alertEl) => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alertEl);
            if (bsAlert) {
                bsAlert.close();
            }
        });
    }, 6000);
});
