---
trigger: glob
globs: "**/*.py"
description: "Pilgrim service: code-conventions — segment 3/3. Mirrors .cursor/rules/code-conventions.mdc."
---

# Pilgrim — code conventions (part 3/3)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/code-conventions.mdc`.

## 13. Admin UI integration rules

### SQLAlchemy Model Admin Integration
**MANDATORY**: Her yeni SQLAlchemy model oluştururken admin interface için gerekli adımları takip et:

#### 1. Enum Fields - SQLAlchemy Enum Kullanımı
```python
# ✅ Correct - Use SQLAlchemy Enum for dropdown support
from sqlalchemy import Enum as SQLEnum

class MyModel(Base):
    status: Mapped[MyStatusEnum] = mapped_column(
        SQLEnum(MyStatusEnum),
        nullable=False,
        default=MyStatusEnum.ACTIVE
    )

# ❌ Wrong - String will show as text input
class MyModel(Base):
    status: Mapped[MyStatusEnum] = mapped_column(
        String(20),  # This won't create dropdown
        nullable=False,
        default=MyStatusEnum.ACTIVE
    )
```

#### 2. Admin Configuration - Model İçin Admin Class Oluşturma
```python
# File: app/admin/config.py

# ✅ Her yeni model için admin class ekle
class MyModelAdmin(ModelView, model=MyModel):
    """Admin interface for MyModel."""
    
    # Listeleme sayfası kolonları
    column_list = [
        MyModel.id, MyModel.name, MyModel.status, 
        MyModel.is_active, MyModel.created_at
    ]
    
    # Arama yapılabilir alanlar
    column_searchable_list = [MyModel.name]
    
    # Sıralanabilir alanlar
    column_sortable_list = [MyModel.name, MyModel.created_at, MyModel.status]
    
    # Filtrelenebilir alanlar (enum'lar dahil)
    column_filters = [MyModel.status, MyModel.is_active]
    
    # Form alanları (oluşturma/düzenleme)
    form_columns = [
        MyModel.name, MyModel.description, MyModel.status,
        MyModel.is_active, MyModel.config_data
    ]
    
    # Genel ayarlar
    can_create = True
    can_edit = True
    can_delete = False  # Genelde delete'i kısıtla
    
    # UI display settings
    name = "My Model"
    name_plural = "My Models"
    icon = "fa-solid fa-cog"  # Font Awesome icon

# setup_admin function'ına ekleme ZORUNLU
def setup_admin(app: FastAPI, engine: AsyncEngine) -> Admin:
    admin = Admin(...)
    
    # ✅ Yeni admin view'ı ekle
    admin.add_view(MyModelAdmin)
    
    return admin
```

#### 3. Enum Definition Pattern
```python
# ✅ Enum'ları models dosyasında tanımla
class MyStatusEnum(str, Enum):
    """Model status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    ERROR = "error"

# ✅ Enum choices helper (isteğe bağlı)
# File: app/admin/form_widgets.py
MY_STATUS_CHOICES = [
    ("active", "Active"),
    ("inactive", "Inactive"), 
    ("pending", "Pending"),
    ("error", "Error")
]
```

#### 4. Migration Pattern for Enums
```python
# ✅ Migration'da enum type'ı oluştur
def upgrade() -> None:
    # Enum type'ı oluştur
    op.execute("CREATE TYPE mystatusenum AS ENUM ('active', 'inactive', 'pending', 'error')")
    
    # Column'ı güncelle
    op.alter_column('my_table', 'status',
                   existing_type=sa.VARCHAR(length=20),
                   type_=sa.Enum('active', 'inactive', 'pending', 'error', name='mystatusenum'),
                   existing_nullable=False)

def downgrade() -> None:
    # Reverse işlemler
    op.alter_column('my_table', 'status',
                   existing_type=sa.Enum('active', 'inactive', 'pending', 'error', name='mystatusenum'),
                   type_=sa.VARCHAR(length=20),
                   existing_nullable=False)
    
    op.execute("DROP TYPE mystatusenum")
```

### Admin UI Development Checklist

#### Model Oluştururken:
- [ ] Enum alanları için `SQLEnum` kullandım
- [ ] Admin class oluşturdum (`app/admin/config.py`)
- [ ] `setup_admin` function'ına view ekledim
- [ ] Migration'da enum type'ları doğru oluşturdum
- [ ] Container restart edip admin UI'da test ettim

#### Enum Eklerken:
- [ ] `str, Enum` inheritance kullandım
- [ ] Model'de `SQLEnum` kullandım
- [ ] Migration'da enum type oluşturdım
- [ ] Admin UI'da dropdown olarak göründüğünü doğruladım

#### Admin Configuration Best Practices:
- [ ] `column_list` - Önemli alanları listele
- [ ] `column_searchable_list` - Arama yapılabilir text alanları
- [ ] `column_filters` - Enum ve boolean alanları
- [ ] `form_columns` - Form'da gösterilecek alanlar
- [ ] `can_create/edit/delete` - İzinleri uygun şekilde ayarla
- [ ] `name/name_plural/icon` - UI görünümü için

### Admin UI Testing Requirements

```python
# ✅ Admin UI enum test örneği
def test_admin_enum_dropdown():
    """Test that enum fields show as dropdowns in admin."""
    response = requests.get("http://localhost:8000/admin/my-model/create")
    
    # Enum field dropdown kontrolü
    assert 'select name="status"' in response.text
    assert 'option value="active"' in response.text
    assert 'option value="inactive"' in response.text
```

### Error Prevention Rules

#### ❌ Common Mistakes to Avoid:
```python
# String kullanımı - dropdown olmaz
status: Mapped[str] = mapped_column(String(20))

# Enum import etmemek
from sqlalchemy import Enum  # ❌ Wrong import

# Admin class'ı setup_admin'e eklememek
def setup_admin(...):
    # admin.add_view(MyModelAdmin)  # ❌ Commented out

# Migration'da enum type oluşturmamak
op.alter_column('table', 'enum_field',
               type_=sa.Enum(...))  # ❌ Type doesn't exist
```

#### ✅ Correct Patterns:
```python
# Doğru enum kullanımı
from sqlalchemy import Enum as SQLEnum
status: Mapped[MyEnum] = mapped_column(SQLEnum(MyEnum))

# Doğru admin setup
admin.add_view(MyModelAdmin)

# Doğru migration
op.execute("CREATE TYPE myenum AS ENUM (...)")
op.alter_column(..., type_=sa.Enum(..., name='myenum'))
```

Following these conventions will ensure consistent and maintainable code throughout the project. Cursor AI will also generate code that adheres to these standards.