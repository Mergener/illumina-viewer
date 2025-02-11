import tkinter as tk
from tkinter import ttk, filedialog, Menu, font
import sqlite3
import chess
from chessboard import display
from datetime import datetime
import time
from functools import cmp_to_key

def compare_trees(t1, t2):
    if t1['depth'] > t2['depth']:
        return -1
    if t1['depth'] < t2['depth']:
        return 1

    if t1['multipv'] < t2['multipv']:
        return -1
    else:
        return 1

    t1_bounds_delta = t1['beta'] - t1['alpha']
    t2_bounds_delta = t2['beta'] - t2['alpha']
    if t1_bounds_delta > t2_bounds_delta:
        return -1
    if t1_bounds_delta < t2_bounds_delta:
        return 1

    return 0

def utc2local(s):
    utc = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    epoch = time.mktime(utc.timetuple())
    offset = datetime.fromtimestamp(epoch) - datetime.utcfromtimestamp(epoch)
    return utc + offset

class ChessTreeVisualizer:
    def __init__(self, root):
        self.root = root
        self.root.title("Illumina Tree Viewer")

        # Database variables.
        self.db_path = None
        self.conn = None
        self.searches = []
        self.selected_search = None
        self.trees = []
        self.selected_tree = None
        self.current_node_index = 1
        self.current_moves = []
        self.current_node_data = {}

        # Initialize GUI components.
        self.create_menu()
        self.create_widgets()

    def create_menu(self):
        menu_bar = Menu(self.root)
        self.root.config(menu=menu_bar)

        file_menu = Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Open Database", command=self.load_database)
        file_menu.add_command(label="Exit", command=self.root.quit)
        menu_bar.add_cascade(label="File", menu=file_menu)

    def create_widgets(self):
        # Database label.
        db_frame = ttk.Frame(self.root)
        db_frame.pack(fill=tk.X, padx=5, pady=5)

        self.db_label = ttk.Label(db_frame, text="No database loaded")
        self.db_label.pack(side=tk.LEFT, padx=5)

        # Search selection.
        search_frame = ttk.Frame(self.root)
        search_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, fill=tk.X)
        self.search_combo = ttk.Combobox(search_frame, state='readonly')
        self.search_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.search_combo.bind('<<ComboboxSelected>>', self.on_search_selected)

        # Tree selection.
        tree_frame = ttk.Frame(self.root)
        tree_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(tree_frame, text="Tree:").pack(side=tk.LEFT)
        self.tree_combo = ttk.Combobox(tree_frame, state='readonly')
        self.tree_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.tree_combo.bind('<<ComboboxSelected>>', self.on_tree_selected)

        # Fen frame
        fen_frame = ttk.Frame(self.root)
        fen_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(fen_frame, text="FEN:").pack(side=tk.LEFT)
        self.fen_entry = tk.Text(fen_frame, height=1)
        self.fen_entry.pack(side=tk.LEFT, fill=tk.X, padx=5, expand=True)
        self.fen_entry.config(state=tk.DISABLED)

        # Navigation buttons.
        nav_frame = ttk.Frame(self.root)
        nav_frame.pack(fill=tk.X, padx=5, pady=5)

        self.back_btn = ttk.Button(nav_frame, text="Back", command=self.go_back, state='disabled')
        self.back_btn.pack(side=tk.LEFT)

        self.child_buttons_frame = ttk.Frame(nav_frame)
        self.child_buttons_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Node details.
        details_frame = ttk.Frame(self.root)
        details_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.node_details_text = tk.Text(details_frame, wrap=tk.WORD)
        self.node_details_text.config(state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(details_frame, orient=tk.VERTICAL, command=self.node_details_text.yview)
        self.node_details_text.configure(yscrollcommand=scrollbar.set)
        self.node_details_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def load_database(self):
        file_path = filedialog.askopenfilename(filetypes=[("SQLite databases", "*.db")])
        if not file_path:
            return
        self.db_path = file_path
        self.db_label.config(text=file_path)
        self.conn = sqlite3.connect(file_path)
        self.conn.row_factory = sqlite3.Row
        self.load_searches()

    def load_searches(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM searches ORDER BY time_of_creation DESC")
        self.searches = cursor.fetchall()
        search_list = [f"{utc2local(row['time_of_creation'])} - {row['root_fen']} (id {row['id']})" for row in self.searches]
        self.search_combo['values'] = search_list
        if self.searches:
            self.search_combo.current(0)
            self.on_search_selected()

    def on_search_selected(self, event=None):
        selected_index = self.search_combo.current()
        if selected_index == -1:
            return
        self.selected_search = self.searches[selected_index]
        self.load_trees()

    def load_trees(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM trees WHERE search = ? ORDER BY root_depth DESC", (self.selected_search['id'],))
        self.trees = cursor.fetchall()
        tree_list = [f"Depth {row['root_depth']} -- a: {row['asp_alpha']} b: {row['asp_beta']} multipv {row['multipv']}" for row in self.trees]
        self.tree_combo['values'] = tree_list
        if self.trees:
            self.tree_combo.current(0)
            self.on_tree_selected()

    def on_tree_selected(self, event=None):
        selected_index = self.tree_combo.current()
        if selected_index == -1:
            return
        self.selected_tree = self.trees[selected_index]
        self.current_node_index = 1
        self.current_moves = []
        self.set_current_node(self.current_node_index)

    def set_current_node(self, node_index):
        self.current_node_index = node_index
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM nodes 
            WHERE tree = ? AND node_index = ?
        """, (self.selected_tree['id'], node_index))
        node = cursor.fetchone()
        self.current_node_data = dict(node) if node else {}
        
        self.update_chessboard()
        self.update_child_buttons()
        self.update_node_details()
        self.update_back_button()

    def update_back_button(self):
        self.back_btn['state'] = 'normal' if self.current_node_index != 1 else 'disabled'

    def go_back(self):
        if self.current_node_index == 1:
            return
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT parent_index FROM nodes 
            WHERE tree = ? AND node_index = ?
        """, (self.selected_tree['id'], self.current_node_index))
        parent_row = cursor.fetchone()
        
        if parent_row:
            parent_index = parent_row['parent_index']
            if parent_index == 0:
                parent_index = 1
            if self.current_moves:
                self.current_moves.pop()
            self.set_current_node(parent_index)

    def get_current_board(self):
        root_fen = self.selected_search['root_fen']
        board = chess.Board(root_fen)
        for move_uci in self.current_moves:
            try:
                move = chess.Move.from_uci(move_uci)
                if move in board.legal_moves or move_uci == '0000':
                    board.push(move)
                else:
                    print(f"Illegal move {move_uci} in position {board.fen()}")
                    break
            except ValueError:
                print(f"Invalid move UCI: {move_uci}")
                break
        return board        

    def update_chessboard(self):
        curr_board = self.get_current_board()
        self.fen_entry.config(state=tk.NORMAL)
        self.fen_entry.delete("1.0", tk.END)
        self.fen_entry.insert(tk.END, curr_board.fen())
        self.fen_entry.config(state=tk.DISABLED)
        display.update(curr_board.fen(), board_display)

    def update_child_buttons(self):
        for widget in self.child_buttons_frame.winfo_children():
            widget.destroy()

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT *
            FROM nodes 
            WHERE tree = ? AND parent_index = ?
            ORDER BY node_index
        """, (self.selected_tree['id'], self.current_node_index))
        children = cursor.fetchall()
        
        best_move = self.current_node_data.get('best_move', '')
        current_board = self.get_current_board()

        num_columns = 10
        style = ttk.Style()
        style.configure("PV.TButton", font=("Arial", 10, "bold")) 
        style.configure("BestMove.TButton", font=("Arial", 10, "bold"), background="lightgreen") 

        for i, child in enumerate(children):
            move = child['last_move']
            is_pv = child['pv'] == 1 
            is_best_move = move == best_move  

            try:
                move_label = current_board.san(current_board.parse_uci(move))
            except:
                move = '0000'
                move_label = 'Null'

            if move == '0000':
                move_label = "Null"

            label = move_label

            skipped_move = child['skip_move']
            if skipped_move != '0000':
                current_board.push_uci(move)
                label += f" (-{current_board.san(current_board.parse_uci(skipped_move))})"
                current_board.pop()

            # Calculate score text
            score = child['score']
            alpha = child['alpha']
            beta = child['beta']
            if score >= beta:
                score_text = f"<= {-score}"
            elif score <= alpha:
                score_text = f">= {-score}"
            else:
                score_text = f"= {-score}"

            # Create container frame for button and label
            container = ttk.Frame(self.child_buttons_frame)
            container.grid(row=i // num_columns, column=i % num_columns, padx=2, pady=2, sticky="nsew")

            # Create button inside container
            btn = ttk.Button(
                container,
                text=label,
                command=lambda idx=child['node_index'], m=move: self.navigate_to_child(idx, m)
            )

            if is_pv:
                btn.configure(style="PV.TButton")
            if is_pv and is_best_move:
                btn.configure(style="BestMove.TButton")  

            btn.pack(side='top', fill='both', expand=True)

            # Create score label
            score_label = ttk.Label(container, text=score_text, font=('Arial', 8), justify='center')
            score_label.pack(side='bottom', fill='x')

        for col in range(min(num_columns, len(children))):
            self.child_buttons_frame.columnconfigure(col, weight=1)

    def navigate_to_child(self, child_index, move):
        self.current_moves.append(move)
        self.set_current_node(child_index)

    def update_node_details(self):
        details = []
        exclude_keys = {'node_index', 'tree', 'parent_index'}
        for key, value in self.current_node_data.items():
            if key not in exclude_keys:
                details.append(self.generate_node_detail_line(key, value))
        self.node_details_text.config(state=tk.NORMAL)
        self.node_details_text.delete(1.0, tk.END)
        self.node_details_text.insert(tk.END, '\n'.join(details))
        self.node_details_text.config(state=tk.DISABLED)

    def generate_node_detail_line(self, key, value):
        def get_prev_board():
            curr_board = self.get_current_board()
            if len(curr_board.move_stack) == 0:
                return None
            curr_board.pop()
            return curr_board

        def uci_to_san(uci_str, board):
            if not board:
                return 'Null'
            move = chess.Move.from_uci(uci_str)
            if not board.is_pseudo_legal(move):
                return 'Null'
            return board.san(move)

        node_detail_value_composers = {
            'qsearch': lambda v: True if v else False,
            'pv': lambda v: True if v else False,
            'last_move': lambda v: uci_to_san(v, get_prev_board()),
            'best_move': lambda v: uci_to_san(v, self.get_current_board()),
            'found_in_tt': lambda v: True if v else False,
            'tt_cutoff': lambda v: True if v else False,
            'improving': lambda v: True if v else False,
            'in_check': lambda v: True if v else False,
            'skip_move': lambda v: uci_to_san(v, self.get_current_board()),
            'tt_bound': lambda v: ['Exact', 'Upperbound', 'Lowerbound'][v],
            'tt_move': lambda v: uci_to_san(v, self.get_current_board()),
        }
        default_composer = lambda v: self.generate_generic_node_detail_value_string(v)

        return f"{key}: {node_detail_value_composers.get(key, default_composer)(value)}"

    def generate_generic_node_detail_value_string(self, v):
        return v

if __name__ == "__main__":
    global board_display
    root = tk.Tk()
    app = ChessTreeVisualizer(root)
    board_display = display.start()
    root.mainloop()
    display.terminate()
    
