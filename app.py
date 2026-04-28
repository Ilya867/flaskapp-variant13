from flask import Flask, render_template, request, redirect, url_for, session
from flask_bootstrap import Bootstrap
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import SubmitField, StringField, BooleanField
from werkzeug.utils import secure_filename
import os
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from datetime import datetime
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
Bootstrap(app)

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

class UploadForm(FlaskForm):
    upload = FileField('Выберите изображение', validators=[
        FileRequired(),
        FileAllowed(['jpg', 'png', 'jpeg'], 'Только изображения!')
    ])
    captcha = StringField('Ответ:')
    add_timestamp = BooleanField('Добавить дату и время на изображение')
    submit = SubmitField('Загрузить и разбить')

def generate_captcha():
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    session['captcha_result'] = num1 + num2
    session['captcha_num1'] = num1
    session['captcha_num2'] = num2
    return f'{num1} + {num2} = ?'

def add_timestamp_to_image(image_path):
    """Добавляет дату и время в правый нижний угол изображения"""
    print(f"=== Функция add_timestamp_to_image вызвана для {image_path} ===")

    # Открываем изображение
    img = Image.open(image_path).convert('RGB')
    draw = ImageDraw.Draw(img)

    # Шрифт
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        print("Шрифт DejaVuSans загружен")
    except:
        font = ImageFont.load_default()
        print("Использую шрифт по умолчанию")

    # Текущая дата и время
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Добавляем дату: {timestamp}")

    # Размер текста
    try:
        bbox = draw.textbbox((0, 0), timestamp, font=font)
        textwidth = bbox[2] - bbox[0]
        textheight = bbox[3] - bbox[1]
    except AttributeError:
        textwidth, textheight = draw.textsize(timestamp, font=font)

    # Позиция (правый нижний угол)
    width, height = img.size
    margin = 10
    x = width - textwidth - margin
    y = height - textheight - margin
    print(f"Размер изображения: {width}x{height}, позиция текста: x={x}, y={y}")

    # Рисуем текст с обводкой
    draw.text((x-1, y-1), timestamp, font=font, fill="black")
    draw.text((x+1, y-1), timestamp, font=font, fill="black")
    draw.text((x-1, y+1), timestamp, font=font, fill="black")
    draw.text((x+1, y+1), timestamp, font=font, fill="black")
    draw.text((x, y), timestamp, font=font, fill="white")

    # Сохраняем
    base, ext = os.path.splitext(image_path)
    new_image_path = f"{base}_timestamp.jpg"
    img.save(new_image_path)
    print(f"Сохранено новое изображение: {new_image_path}")

    return new_image_path

def split_image(image_path):
    img = Image.open(image_path).convert('RGB')
    width, height = img.size
    half_width = width // 2
    half_height = height // 2

    boxes = [
        (0, 0, half_width, half_height),
        (half_width, 0, width, half_height),
        (0, half_height, half_width, height),
        (half_width, half_height, width, height)
    ]

    part_paths = []
    for i, box in enumerate(boxes):
        part = img.crop(box)
        part_filename = f'part_{i+1}_{os.path.basename(image_path)}'
        part_filepath = os.path.join(app.config['UPLOAD_FOLDER'], part_filename)
        part.save(part_filepath)
        part_paths.append(part_filepath)

    return part_paths

def plot_color_distribution(image_path):
    img = Image.open(image_path).convert('RGB')
    img_array = np.array(img)

    colors = ('r', 'g', 'b')
    channel_ids = (0, 1, 2)

    plt.figure(figsize=(10, 5))

    for channel_id, color in zip(channel_ids, colors):
        histogram, bin_edges = np.histogram(img_array[:, :, channel_id], bins=256, range=(0, 256))
        plt.plot(bin_edges[0:-1], histogram, color=color, label=f'{color.upper()} канал')

    plt.title('Гистограмма распределения цветов')
    plt.xlabel('Значение пикселя')
    plt.ylabel('Частота')
    plt.xlim([0, 256])
    plt.legend()
    plt.grid(True, alpha=0.3)

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plot_data = base64.b64encode(buf.getvalue()).decode('ascii')
    plt.close()

    return f'data:image/png;base64,{plot_data}'

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        generate_captcha()

    captcha_question = f"{session.get('captcha_num1', 5)} + {session.get('captcha_num2', 3)} = ?"
    form = UploadForm()

    if request.method == 'POST':
        print("=== POST запрос ===")
        print(f"Все поля формы: {list(request.form.keys())}")
        print(f"Значение add_timestamp: {request.form.get('add_timestamp')}")

        if 'upload' not in request.files:
            return render_template('index.html', form=form, error='Выберите файл!', captcha_question=captcha_question)

        file = request.files['upload']
        if file.filename == '':
            return render_template('index.html', form=form, error='Выберите файл!', captcha_question=captcha_question)

        captcha_answer = request.form.get('captcha', '').strip()
        expected_result = session.get('captcha_result', 0)

        try:
            if int(captcha_answer) == expected_result:
                filename = 'original_' + secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                print(f"Файл сохранен: {filepath}")

                # Проверяем чекбокс
                add_ts = request.form.get('add_timestamp') == 'on' or request.form.get('add_timestamp') == 'y'
                print(f"Добавить дату? {add_ts}")

                if add_ts:
                    print("Вызвана функция добавления даты")
                    filepath = add_timestamp_to_image(filepath)
                    filename = os.path.basename(filepath)
                    print(f"Новое имя файла с датой: {filename}")
                else:
                    print("Чекбокс не отмечен, дата не добавлена")

                generate_captcha()
                return redirect(url_for('result', filename=filename))
            else:
                generate_captcha()
                return render_template('index.html', form=form, error='Неверный ответ на капчу!', captcha_question=f"{session.get('captcha_num1', 5)} + {session.get('captcha_num2', 3)} = ?")
        except ValueError:
            generate_captcha()
            return render_template('index.html', form=form, error='Введите число!', captcha_question=f"{session.get('captcha_num1', 5)} + {session.get('captcha_num2', 3)} = ?")

    return render_template('index.html', form=form, captcha_question=captcha_question)

@app.route('/result/<filename>')
def result(filename):
    original_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if not os.path.exists(original_path):
        return "Изображение не найдено", 404

    part_paths = split_image(original_path)
    original_plot = plot_color_distribution(original_path)

    part_plots = []
    for part_path in part_paths:
        part_plots.append(plot_color_distribution(part_path))

    original_url = url_for('static', filename=f'uploads/{filename}')

    part_urls = []
    for path in part_paths:
        part_filename = os.path.basename(path)
        part_url = url_for('static', filename=f'uploads/{part_filename}')
        part_urls.append(part_url)

    return render_template('result.html',
                         original_url=original_url,
                         part_urls=part_urls,
                         original_plot=original_plot,
                         part_plots=part_plots)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
