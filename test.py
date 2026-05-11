import matplotlib.pyplot as plt
import matplotlib.patches as patches


def draw_pipeline_diagram():
    # Configuration
    fig, axs = plt.subplots(3, 1, figsize=(14, 12))
    fig.subplots_adjust(hspace=0.5)

    # Color palette
    colors = {
        'IF': '#E3F2FD',  # Light Blue
        'ID': '#FFF9C4',  # Light Yellow
        'EX': '#C8E6C9',  # Light Green
        'MEM': '#FFCCBC',  # Light Orange
        'WB': '#D1C4E9',  # Light Purple
        'Stall': '#EEEEEE'  # Grey
    }

    scenarios = [
        {"title": "Scenario 1: RAW Hazard (No Forwarding / Stalls Required)", "cycles": 10},
        {"title": "Scenario 2: RAW Hazard (With ALU Data Forwarding)", "cycles": 8},
        {"title": "Scenario 3: Load-Use Hazard (Forwarding + 1 Mandatory Stall)", "cycles": 9}
    ]

    def draw_instruction(ax, row, instr_name, stages, start_col):
        # Add instruction text on the left
        ax.text(0.5, row + 0.5, instr_name, ha='right', va='center', fontsize=11, fontweight='bold', family='monospace')

        # Draw the stage blocks
        box_width = 0.8
        box_height = 0.6
        for i, stage in enumerate(stages):
            col = start_col + i
            color = colors.get(stage, colors['Stall'])

            # Draw rectangle
            rect = patches.Rectangle((col + 0.1, row + 0.2), box_width, box_height,
                                     linewidth=1.5, edgecolor='#424242', facecolor=color, zorder=2)

            # Hash pattern for stalls
            if stage == 'Stall':
                rect.set_hatch('////')

            ax.add_patch(rect)

            # Add text inside block
            ax.text(col + 0.5, row + 0.5, stage, ha='center', va='center',
                    fontsize=10, fontweight='bold', color='#212121', zorder=3)

    def setup_axis(ax, title, num_cycles):
        ax.set_xlim(0, num_cycles + 1)
        ax.set_ylim(-0.5, 3)
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.axis('off')

        # Draw cycle headers and grid lines
        for i in range(1, num_cycles + 1):
            ax.text(i + 0.5, 3.2, f'Cycle {i}', ha='center', va='center', fontsize=11, fontweight='bold')
            ax.axvline(x=i, color='#E0E0E0', linestyle='--', zorder=1)
        ax.axvline(x=num_cycles + 1, color='#E0E0E0', linestyle='--', zorder=1)

    # ==========================================
    # Plot 1: Stalls (Split-Cycle at WB/ID)
    # ==========================================
    ax = axs[0]
    setup_axis(ax, scenarios[0]["title"], scenarios[0]["cycles"])

    # Rows go from bottom to top in matplotlib coordinates (0 is bottom)
    draw_instruction(ax, 2, "SUB X2, X1, X3", ['IF', 'ID', 'EX', 'MEM', 'WB'], 1)
    draw_instruction(ax, 1, "AND X12, X2, X5", ['IF', 'Stall', 'Stall', 'ID', 'EX', 'MEM', 'WB'], 2)
    draw_instruction(ax, 0, "OR  X13, X6, X2", ['Stall', 'Stall', 'IF', 'Stall', 'ID', 'EX', 'MEM', 'WB'], 2)

    # Split cycle annotation
    ax.annotate('', xy=(4.5, 1.8), xytext=(5.5, 2.2),
                arrowprops=dict(facecolor='red', edgecolor='red', arrowstyle='->', lw=2,
                                connectionstyle="arc3,rad=-0.2"))
    ax.text(6.0, 2.0, "Split-Cycle:\nWB writes 1st half,\nID reads 2nd half.", color='red', fontsize=10, va='center')

    # ==========================================
    # Plot 2: ALU Forwarding
    # ==========================================
    ax = axs[1]
    setup_axis(ax, scenarios[1]["title"], scenarios[1]["cycles"])

    draw_instruction(ax, 2, "SUB X2, X1, X3", ['IF', 'ID', 'EX', 'MEM', 'WB'], 1)
    draw_instruction(ax, 1, "AND X12, X2, X5", ['IF', 'ID', 'EX', 'MEM', 'WB'], 2)
    draw_instruction(ax, 0, "OR  X13, X6, X2", ['IF', 'ID', 'EX', 'MEM', 'WB'], 3)

    # EX to EX Forwarding Arrow
    ax.annotate('', xy=(4.5, 1.8), xytext=(3.5, 2.2),
                arrowprops=dict(facecolor='blue', edgecolor='blue', arrowstyle='->', lw=2))

    # MEM to EX Forwarding Arrow
    ax.annotate('', xy=(5.5, 0.8), xytext=(4.5, 2.2),
                arrowprops=dict(facecolor='green', edgecolor='green', arrowstyle='->', lw=2))

    ax.text(5.5, 2.6, "Data forwarded from EX pipeline register", color='blue', fontsize=10)
    ax.text(6.5, 1.6, "Data forwarded from MEM pipeline register", color='green', fontsize=10)

    # ==========================================
    # Plot 3: Load-Use Hazard
    # ==========================================
    ax = axs[2]
    setup_axis(ax, scenarios[2]["title"], scenarios[2]["cycles"])

    draw_instruction(ax, 2, "LW  X2, 0(X1)", ['IF', 'ID', 'EX', 'MEM', 'WB'], 1)
    draw_instruction(ax, 1, "ADD X5, X2, X3", ['IF', 'ID', 'Stall', 'EX', 'MEM', 'WB'], 2)

    # Load-Use Forwarding Arrow (MEM to EX)
    ax.annotate('', xy=(5.5, 1.8), xytext=(4.5, 2.2),
                arrowprops=dict(facecolor='#D84315', edgecolor='#D84315', arrowstyle='->', lw=2))

    ax.text(5.5, 2.6, "Data is not available until MEM stage.\n1-cycle stall is mandatory before forwarding.",
            color='#D84315', fontsize=10)

    # Save the output
    plt.savefig('pipeline_hazards_reference.png', bbox_inches='tight', dpi=300)
    print("Execution complete: High-resolution image saved as 'pipeline_hazards_reference.png'.")


if __name__ == "__main__":
    draw_pipeline_diagram()