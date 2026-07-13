import os
import time
from datetime import datetime
from PIL import Image
import img2pdf
from playwright.sync_api import sync_playwright

def find_page_bounds(image_path):
    try:
        img = Image.open(image_path)
    except Exception:
        return None

    gray = img.convert("L")
    width, height = gray.size
    
    bg_color = gray.getpixel((10, height // 2))
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
    
    return (page_cols[0], page_rows[0], page_cols[-1] - page_cols[0], page_rows[-1] - page_rows[0])

def main():
    print("Starting optimized headless scraper...")
    with sync_playwright() as p:
        # Invisible high-DPI virtual monitor for ultra HD captures
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1400, 'height': 1200},
            device_scale_factor=2 
        )
        
        page = context.new_page()
        page.goto("https://usachemcamp.com/question-of-the-week", wait_until="networkidle")
        
        button = page.locator('a:has-text("QOW_12JULY_PROBLEMS")').first
        button.wait_for(state="visible", timeout=10000)
        
        doc_url = button.get_attribute("href")
        print(f"Found Google Doc URL: {doc_url}")
        
        doc_page = context.new_page()
        doc_page.goto(doc_url, wait_until="networkidle")
        
        try:
            doc_page.wait_for_selector('[aria-label="Zoom out"], [data-tooltip="Zoom out"]', timeout=30000)
        except Exception:
            pass
        
        try:
            doc_page.evaluate("""
                let z = document.querySelector('input[aria-label*="Zoom"]');
                if (!z) z = Array.from(document.querySelectorAll('input')).find(i => i.value.includes('%') || i.value === 'Fit' || i.value === '100%');
                if (!z) z = document.querySelector('[role="combobox"][aria-label*="Zoom"], [title*="Zoom"] input');
                if (z) {
                    z.focus();
                    z.click();
                    if (typeof z.select === 'function') z.select();
                }
            """)
            time.sleep(0.2)
            
            doc_page.keyboard.press("Control+A")
            doc_page.keyboard.press("Backspace")
            doc_page.keyboard.type("100")
            doc_page.keyboard.press("Enter")
            time.sleep(0.5)
        except Exception as e:
            print(f"Could not directly type zoom level: {e}")

        output_dir = "qotw"
        os.makedirs(output_dir, exist_ok=True)
        images = []
        
        total_pages = 20
        try:
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
            pass
        
        for i in range(total_pages):
            screenshot_path = os.path.join(output_dir, f"temp_full_{i}.png")
            doc_page.screenshot(path=screenshot_path)
            
            bounds = find_page_bounds(screenshot_path)
            if bounds:
                x, y, w, h = bounds
                img = Image.open(screenshot_path)
                cropped = img.crop((x, y, x+w, y+h))
                
                crop_path = os.path.join(output_dir, f"page_{i+1}.png")
                cropped.save(crop_path)
                images.append(crop_path)
                print(f"Captured page {i+1} of {total_pages}")
            
            if i < total_pages - 1:
                try:
                    next_btn = doc_page.locator('[aria-label="Next page"], [data-tooltip="Next page"], [title="Next page"]').first
                    if next_btn.count() > 0:
                        next_btn.click(force=True)
                    else:
                        doc_page.keyboard.press("PageDown")
                except Exception:
                    doc_page.keyboard.press("PageDown")
                time.sleep(0.5)
            
        if images:
            date_str = datetime.now().strftime("%Y-%m-%d")
            pdf_path = os.path.join(output_dir, f"{date_str}.pdf")
            
            print(f"Assembling {len(images)} images into {pdf_path}...")
            pdf_bytes = img2pdf.convert(images)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
                
            print("Cleaning up temporary images...")
            for img_path in images:
                os.remove(img_path)
            for i in range(total_pages):
                tmp = os.path.join(output_dir, f"temp_full_{i}.png")
                if os.path.exists(tmp):
                    os.remove(tmp)
        
        browser.close()

if __name__ == "__main__":
    main()
