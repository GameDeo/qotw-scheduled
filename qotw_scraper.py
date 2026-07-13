import os
import time
from datetime import datetime
from PIL import Image, ImageChops
import img2pdf
from playwright.sync_api import sync_playwright

def find_page_bounds(image_path):
    """
    Algorithmically identifies the bounds of the white page on the dark background using Pillow.
    Uses pixel density projection and contiguous blocks to perfectly hug the page boundaries.
    """
    try:
        img = Image.open(image_path)
    except Exception:
        return None

    # Convert to grayscale
    gray = img.convert("L")
    width, height = gray.size
    
    # Sample the background color from the left edge (middle vertically)
    bg_color = gray.getpixel((10, height // 2))
    
    # Binarize: Any pixel differing from background > 8 is foreground (page/text/UI)
    thresh = gray.point(lambda p: 255 if abs(p - bg_color) > 8 else 0)
    pixels = thresh.load()
    
    row_sums = [0] * height
    col_sums = [0] * width
    
    for y in range(height):
        for x in range(width):
            if pixels[x, y] == 255:
                row_sums[y] += 1
                col_sums[x] += 1
                
    min_page_width = width * 0.10
    min_page_height = height * 0.10
    
    valid_rows = [y for y, s in enumerate(row_sums) if s > min_page_width]
    valid_cols = [x for x, s in enumerate(col_sums) if s > min_page_height]
    
    if not valid_rows or not valid_cols:
        return None
        
    def largest_contiguous_block(indices):
        blocks = []
        current = [indices[0]]
        for i in range(1, len(indices)):
            if indices[i] == indices[i-1] + 1:
                current.append(indices[i])
            else:
                blocks.append(current)
                current = [indices[i]]
        blocks.append(current)
        return max(blocks, key=len)
        
    page_rows = largest_contiguous_block(valid_rows)
    page_cols = largest_contiguous_block(valid_cols)
    
    top = page_rows[0]
    bottom = page_rows[-1]
    left = page_cols[0]
    right = page_cols[-1]
    
    w = right - left
    h = bottom - top
    
    if w < 100 or h < 100:
        return None
        
    return (left, top, w, h)

# --- UI Helper Functions ---
def set_overlay_text(page, text):
    try:
        page.evaluate(f"""
            if (!document.getElementById('playwright-overlay')) {{
                const div = document.createElement('div');
                div.id = 'playwright-overlay';
                div.style.position = 'fixed';
                div.style.top = '20px';
                div.style.right = '20px';
                div.style.padding = '15px 25px';
                div.style.backgroundColor = 'rgba(0, 0, 0, 0.85)';
                div.style.color = '#00ff00';
                div.style.fontSize = '22px';
                div.style.fontWeight = 'bold';
                div.style.zIndex = '2147483647';
                div.style.pointerEvents = 'none';
                div.style.border = '2px solid #00ff00';
                div.style.borderRadius = '8px';
                div.style.fontFamily = 'monospace';
                div.style.boxShadow = '0 0 15px rgba(0, 255, 0, 0.5)';
                document.body.appendChild(div);
            }}
            document.getElementById('playwright-overlay').innerText = `{text}`;
            // Add a red border to the HTML element to highlight the active window
            document.documentElement.style.boxSizing = 'border-box';
            document.documentElement.style.border = '6px solid red';
        """)
    except Exception:
        pass

def hide_ui_for_screenshot(page):
    try:
        page.evaluate("""
            const el = document.getElementById('playwright-overlay');
            if (el) el.style.display = 'none';
            document.documentElement.style.border = 'none';
            // Hide any lingering bounding boxes just in case
            document.querySelectorAll('.playwright-bbox').forEach(e => e.style.display = 'none');
        """)
    except Exception:
        pass

def restore_ui_after_screenshot(page):
    try:
        page.evaluate("""
            const el = document.getElementById('playwright-overlay');
            if (el) el.style.display = 'block';
            document.documentElement.style.border = '6px solid red';
            document.querySelectorAll('.playwright-bbox').forEach(e => e.style.display = 'block');
        """)
    except Exception:
        pass

def highlight_bounding_box(page, x, y, w, h):
    try:
        page.evaluate(f"""
            const dpr = window.devicePixelRatio || 1;
            const box = document.createElement('div');
            box.className = 'playwright-bbox';
            box.style.position = 'fixed';
            box.style.left = ({x} / dpr) + 'px';
            box.style.top = ({y} / dpr) + 'px';
            box.style.width = ({w} / dpr) + 'px';
            box.style.height = ({h} / dpr) + 'px';
            box.style.border = '4px solid #ff00ff';
            box.style.backgroundColor = 'rgba(255, 0, 255, 0.15)';
            box.style.zIndex = '2147483646';
            box.style.pointerEvents = 'none';
            box.style.boxShadow = '0 0 20px #ff00ff';
            document.body.appendChild(box);
            
            // Auto-remove after 1.5 seconds
            setTimeout(() => box.remove(), 1500);
        """)
    except Exception:
        pass
# ---------------------------

def main():
    with sync_playwright() as p:
        # Launch maximized
        browser = p.chromium.launch(headless=False, args=['--start-maximized'])
        context = browser.new_context(no_viewport=True)

        time.sleep(0.2)
        
        # 1. Navigate to the website
        page = context.new_page()
        set_overlay_text(page, "Step 1: Navigating to QOTW page...")
        print("Navigating to Question of the Week page...")
        page.goto("https://usachemcamp.com/question-of-the-week", wait_until="networkidle")
        
        # 2. Extract the link to the QOTW google doc
        set_overlay_text(page, "Step 2: Looking for button...")
        print("Looking for the 'QOW_12JULY_PROBLEMS' button...")
        button = page.locator('a:has-text("QOW_12JULY_PROBLEMS")').first
        button.wait_for(state="visible", timeout=10000)
        
        # Add a brief highlight to the button so you can see it
        button.evaluate("el => el.style.boxShadow = '0 0 20px 10px #ff00ff'")
        time.sleep(0.2)
        
        doc_url = button.get_attribute("href")
        print(f"Found Google Doc URL: {doc_url}")
        
        # 3. Launch a new browser window open to the QOTW doc
        set_overlay_text(page, "Step 3: Opening Google Doc...")
        print("Opening the Google Doc...")
        doc_page = context.new_page()
        doc_page.goto(doc_url, wait_until="networkidle")
        
        # Wait for the PDF viewer to load
        set_overlay_text(doc_page, "Step 4: Waiting for PDF to load...")
        try:
            # Wait specifically for the zoom controls to appear instead of a generic toolbar
            doc_page.wait_for_selector('[aria-label="Zoom out"], [data-tooltip="Zoom out"]', timeout=30000)
        except Exception:
            print("Warning: Could not find standard toolbar, continuing anyway...")
        time.sleep(0.5)
        
        # 4. Set the Google Docs zoom to 65%
        set_overlay_text(doc_page, "Step 5: Adjusting zoom level...")
        print("Setting zoom to 65%...")
        
        try:
            # We use JS to aggressively find the zoom input field since Drive DOM is obfuscated
            doc_page.evaluate("""
                let z = document.querySelector('input[aria-label*="Zoom"]');
                if (!z) z = Array.from(document.querySelectorAll('input')).find(i => i.value.includes('%') || i.value === 'Fit' || i.value === '100%');
                if (!z) z = document.querySelector('[role="combobox"][aria-label*="Zoom"], [title*="Zoom"] input');
                if (z) {
                    z.style.boxShadow = '0 0 20px #00ff00'; // Highlight it
                    z.focus();
                    z.click();
                    if (typeof z.select === 'function') z.select();
                }
            """)
            time.sleep(0.2)
            
            # Use Playwright keyboard to simulate human typing
            doc_page.keyboard.press("Control+A")
            time.sleep(0.1)
            doc_page.keyboard.press("Backspace")
            doc_page.keyboard.type("65", delay=20) # Type fast
            doc_page.keyboard.press("Enter")
            time.sleep(0.2)
        except Exception as e:
            print(f"Could not directly type zoom level: {e}")
                
        set_overlay_text(doc_page, "Zoom set! Waiting to render...")
        time.sleep(0.5)

        print("Capturing pages...")
        output_dir = "qotw"
        os.makedirs(output_dir, exist_ok=True)
        
        images = []
        
        total_pages = 20
        try:
            # We use a broad regex on the entire page's visible text to find the page indicator (e.g. " / 5")
            parsed_total = doc_page.evaluate("""() => {
                const text = document.body.innerText.replace(/\\s+/g, ' ');
                const match = text.match(/\\/\\s*(\\d+)/);
                if (match) return parseInt(match[1]);
                return null;
            }""")
            if parsed_total:
                total_pages = parsed_total
                print(f"Detected document length: {total_pages} pages")
        except Exception:
            print("Could not parse total pages from UI, defaulting to 20 maximum.")
        
        for i in range(total_pages):
            set_overlay_text(doc_page, f"Step 6: Taking screenshot of Page {i+1} of {total_pages}...")
            
            # Hide the UI right before taking screenshot so it doesn't get captured!
            hide_ui_for_screenshot(doc_page)
            time.sleep(0.1) # brief pause to let DOM hide elements
            
            screenshot_path = os.path.join(output_dir, f"temp_full_{i}.png")
            doc_page.screenshot(path=screenshot_path)
            
            # Restore UI immediately after
            restore_ui_after_screenshot(doc_page)
            
            set_overlay_text(doc_page, f"Step 7: Processing bounds for Page {i+1}...")
            bounds = find_page_bounds(screenshot_path)
            
            if bounds:
                x, y, w, h = bounds
                
                # Highlight bounds but don't sleep
                set_overlay_text(doc_page, f"Page {i+1} bounds found! Cropping...")
                highlight_bounding_box(doc_page, x, y, w, h)
                
                img = Image.open(screenshot_path)
                cropped = img.crop((x, y, x+w, y+h))
                
                crop_path = os.path.join(output_dir, f"page_{i+1}.png")
                cropped.save(crop_path)
                images.append(crop_path)
                print(f"Captured page {i+1} of {total_pages}")
            else:
                set_overlay_text(doc_page, f"Warning: No bounds found for Page {i+1}!")
                print(f"Could not identify page bounds for page {i+1}")
            
            set_overlay_text(doc_page, f"Step 8: Jumping to next page...")
            if i < total_pages - 1: # Don't scroll on the last page
                # Clicking the "Next page" button guarantees perfect page alignment!
                try:
                    next_btn = doc_page.locator('[aria-label="Next page"], [data-tooltip="Next page"], [title="Next page"]').first
                    if next_btn.count() > 0:
                        next_btn.click(force=True)
                    else:
                        doc_page.keyboard.press("PageDown") # Fallback
                except Exception:
                    doc_page.keyboard.press("PageDown")
                
                # Google Drive renders pages relatively quickly
                time.sleep(0.5)
            
        if images:
            set_overlay_text(doc_page, "Step 9: Assembling PDF...")
            date_str = datetime.now().strftime("%Y-%m-%d")
            pdf_path = os.path.join(output_dir, f"{date_str}.pdf")
            
            print(f"Assembling {len(images)} images into {pdf_path}...")
            pdf_bytes = img2pdf.convert(images)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
                
            set_overlay_text(doc_page, "Done! Cleaning up...")
            print("Done! Cleaning up temporary images...")
            time.sleep(1)
            
            for img_path in images:
                os.remove(img_path)
            for i in range(total_pages):
                tmp = os.path.join(output_dir, f"temp_full_{i}.png")
                if os.path.exists(tmp):
                    os.remove(tmp)
        else:
            set_overlay_text(doc_page, "Finished. No pages captured.")
            print("No pages were captured.")
            time.sleep(1)
            
        browser.close()

if __name__ == "__main__":
    main()
