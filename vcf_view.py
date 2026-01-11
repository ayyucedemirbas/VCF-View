import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTableView, QHeaderView, QPushButton, 
                             QFileDialog, QLabel, QLineEdit, QSplitter, 
                             QFrame, QTextEdit, QCheckBox)
from PyQt6.QtCore import Qt, QAbstractTableModel, QRectF
from PyQt6.QtGui import QColor, QIcon, QPixmap, QPainter, QBrush, QPen, QFont, QRadialGradient

try:
    import pysam
    HAS_PYSAM = True
except ImportError:
    HAS_PYSAM = False

STYLESHEET = """
QMainWindow { background-color: #1e1e1e; }
QWidget { color: #e0e0e0; font-family: 'SF Pro Text', 'Helvetica Neue', sans-serif; font-size: 13px; }
QTableView { 
    background-color: #252526; 
    gridline-color: #333333; 
    border: none; 
    selection-background-color: #375a7f; 
    selection-color: white; 
    alternate-background-color: #2d2d30; 
}
QHeaderView::section { 
    background-color: #333333; 
    color: #cccccc; 
    padding: 6px; 
    border: none; 
    border-right: 1px solid #404040; 
    font-weight: bold; 
}
QFrame#Sidebar { background-color: #252526; border-right: 1px solid #333333; }
QPushButton { background-color: #007acc; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold; }
QPushButton:hover { background-color: #0062a3; }
QLineEdit { background-color: #3c3c3c; border: 1px solid #555555; color: white; padding: 5px; border-radius: 3px; }
QTextEdit { background-color: #1e1e1e; border: 1px solid #333333; color: #ce9178; font-family: 'Menlo', 'Monaco', monospace; }
QLabel#Heading { font-size: 16px; font-weight: bold; color: #ffffff; margin-bottom: 10px; }
"""

def create_app_icon():
    size = 512
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    path = QRectF(20, 20, size-40, size-40)
    
    gradient = QRadialGradient(size/2, size/2, size/2)
    gradient.setColorAt(0, QColor("#0099ff"))
    gradient.setColorAt(1, QColor("#005a9e"))
    
    painter.setBrush(QBrush(gradient))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(path, 110, 110) 
    
    # 2. Text "VCF"
    painter.setPen(QColor("#ffffff"))
    font = QFont("Helvetica Neue", 180, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(path, Qt.AlignmentFlag.AlignCenter, "VCF")
    
    painter.end()
    return QIcon(pixmap)

class VcfTableModel(QAbstractTableModel):
    def __init__(self, variants=None):
        super().__init__()
        self._data = variants or []
        self._headers = ["CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            row_data = self._data[index.row()]
            col = index.column()
            
            if col == 0: return row_data['chrom']
            elif col == 1: return str(row_data['pos'])
            elif col == 2: return row_data['id'] if row_data['id'] else "."
            elif col == 3: return row_data['ref']
            elif col == 4: return row_data['alt']
            elif col == 5: return str(round(row_data['qual'], 2)) if row_data['qual'] else "."
            elif col == 6: return row_data['filter']
            elif col == 7: return row_data['info']
            
        elif role == Qt.ItemDataRole.BackgroundRole:
            if index.row() % 2 == 1:
                return QColor("#2d2d30")
        
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() in [1, 5]: 
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    def rowCount(self, index):
        return len(self._data)

    def columnCount(self, index):
        return len(self._headers)

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._headers[section]

    def set_data(self, new_data):
        self.beginResetModel()
        self._data = new_data
        self.endResetModel()

    def get_variant(self, row_idx):
        return self._data[row_idx]

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ProGen VCF Viewer")
        self.resize(1300, 850)
        self.setStyleSheet(STYLESHEET)
        
        self.all_variants = []
        self.filtered_variants = []
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(250)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(15, 20, 15, 20)
        
        title_lbl = QLabel("VCF Controls")
        title_lbl.setObjectName("Heading")
        side_layout.addWidget(title_lbl)

        self.btn_load = QPushButton("Load VCF File")
        self.btn_load.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load.clicked.connect(self.load_vcf)
        side_layout.addWidget(self.btn_load)
        
        side_layout.addSpacing(20)
        
        side_layout.addWidget(QLabel("Filters"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Chrom/ID/Info...")
        self.search_input.textChanged.connect(self.apply_filters)
        side_layout.addWidget(self.search_input)
        
        self.chk_pass = QCheckBox("Show PASS Only")
        self.chk_pass.stateChanged.connect(self.apply_filters)
        side_layout.addWidget(self.chk_pass)

        side_layout.addSpacing(20)
        
        self.lbl_count = QLabel("Variants: 0")
        side_layout.addWidget(self.lbl_count)
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: #888; font-style: italic;")
        side_layout.addWidget(self.lbl_status)
        side_layout.addStretch()
        
        content_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.table_view = QTableView()
        self.model = VcfTableModel()
        self.table_view.setModel(self.model)
        
        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True) 
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.setShowGrid(False)
        self.table_view.selectionModel().selectionChanged.connect(self.on_selection_changed)
        
        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setPlaceholderText("Select a variant to view full details...")
        
        content_splitter.addWidget(self.table_view)
        content_splitter.addWidget(self.detail_view)
        content_splitter.setSizes([600, 200])
        
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(content_splitter)

    def load_vcf(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open VCF", "", "VCF Files (*.vcf *.vcf.gz);;All Files (*)")
        if not file_path: return

        self.lbl_status.setText("Parsing...")
        QApplication.processEvents()

        self.all_variants = []
        try:
            if HAS_PYSAM: self.parse_with_pysam(file_path)
            else: self.parse_native(file_path)
            self.apply_filters()
            self.lbl_status.setText(f"Loaded: {os.path.basename(file_path)}")
        except Exception as e:
            self.lbl_status.setText("Error loading file")
            self.detail_view.setText(f"Error:\n{str(e)}")

    def parse_with_pysam(self, path):
        vcf = pysam.VariantFile(path)
        for rec in vcf:
            flt = list(rec.filter.keys())
            flt_str = "PASS" if not flt or "PASS" in flt else ";".join(flt)
            alt_str = ",".join([str(a) for a in rec.alts]) if rec.alts else "."
            
            info_parts = []
            for k, v in rec.info.items():
                if isinstance(v, bool) and v:
                    info_parts.append(k)
                elif isinstance(v, (list, tuple)):
                    val_str = ",".join(map(str, v))
                    info_parts.append(f"{k}={val_str}")
                else:
                    info_parts.append(f"{k}={v}")
            info_str = ";".join(info_parts)

            self.all_variants.append({
                'chrom': rec.chrom,
                'pos': rec.pos,
                'id': rec.id,
                'ref': rec.ref,
                'alt': alt_str,
                'qual': rec.qual,
                'filter': flt_str,
                'info': info_str,
                'raw_info': str(rec)
            })
        vcf.close()

    def parse_native(self, path):
        import gzip
        opener = gzip.open if path.endswith('.gz') else open
        with opener(path, 'rt', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#'): continue
                cols = line.strip().split('\t')
                if len(cols) < 8: continue
                try: qual = float(cols[5]) if cols[5] != '.' else 0.0
                except: qual = 0.0
                self.all_variants.append({
                    'chrom': cols[0],
                    'pos': int(cols[1]),
                    'id': cols[2],
                    'ref': cols[3],
                    'alt': cols[4],
                    'qual': qual,
                    'filter': cols[6],
                    'info': cols[7],
                    'raw_info': line
                })

    def apply_filters(self):
        search_text = self.search_input.text().lower()
        show_pass = self.chk_pass.isChecked()
        self.filtered_variants = []
        for v in self.all_variants:
            if show_pass and v['filter'] != "PASS": continue
            if search_text:
                if (search_text not in v['chrom'].lower() and 
                    search_text not in str(v['pos']) and 
                    search_text not in str(v['id']).lower() and
                    search_text not in v['info'].lower()):
                    continue
            self.filtered_variants.append(v)
        self.model.set_data(self.filtered_variants)
        self.lbl_count.setText(f"Variants: {len(self.filtered_variants)}")
        header = self.table_view.horizontalHeader()
        header.resizeSection(0, 80)
        header.resizeSection(1, 100)
        header.resizeSection(2, 100)
        header.resizeSection(3, 50)
        header.resizeSection(4, 50)
        header.resizeSection(5, 60)
        header.resizeSection(6, 60)

    def on_selection_changed(self):
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes: return
        variant = self.model.get_variant(indexes[0].row())
        info_text = f"=== Variant Details ===\n"
        info_text += f"Location: {variant['chrom']}:{variant['pos']}\n"
        info_text += f"Ref/Alt:  {variant['ref']} -> {variant['alt']}\n"
        info_text += f"Quality:  {variant['qual']}\n"
        info_text += f"Filter:   {variant['filter']}\n"
        info_text += f"Info:     {variant['info']}\n"
        info_text += "-" * 30 + "\n"
        info_text += f"Raw Line:\n{variant['raw_info'].replace(chr(9), ' ')}"
        self.detail_view.setText(info_text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    #app_icon = create_app_icon()
    app_icon = QIcon("vcf_logo.png") 
    app.setWindowIcon(app_icon)
    
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
