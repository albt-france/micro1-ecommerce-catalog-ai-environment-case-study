-- Relational model of the unified catalogue (DuckDB; PostgreSQL notes in comments).
-- One product (parent) has one or more variants (SKU = colour/size combination). Prices, stock, source lineage and
-- long-tail attributes live in their own tables. Loaded and checked by src/build_schema.py.

CREATE TABLE brand (
    brand_id      INTEGER PRIMARY KEY,
    name          VARCHAR NOT NULL UNIQUE,            -- display spelling chosen by the brand mapping table
    brand_key     VARCHAR NOT NULL UNIQUE             -- folded key used for matching ('amazonbasics')
);

CREATE TABLE brand_alias (                           -- every raw spelling seen in a source -> one brand
    alias         VARCHAR PRIMARY KEY,
    brand_id      INTEGER NOT NULL REFERENCES brand (brand_id),
    method        VARCHAR NOT NULL CHECK (method IN ('reference', 'variant', 'fuzzy', 'new'))
);

CREATE TABLE category (                              -- navigation tree as an adjacency list
    category_id         VARCHAR PRIMARY KEY,
    parent_id           VARCHAR REFERENCES category (category_id),
    name                VARCHAR NOT NULL,
    level               SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 4),
    path                VARCHAR NOT NULL UNIQUE,      -- 'Home & Furniture > Living Room Furniture > Sofas & Couches'
    is_leaf             BOOLEAN NOT NULL,
    google_category_id  INTEGER,                      -- Google Product Taxonomy id (leaves only)
    attribute_template  VARCHAR                       -- see taxonomy/category_attributes.yaml
);

CREATE TABLE attribute (
    attribute_code  VARCHAR PRIMARY KEY,              -- 'colour', 'size', 'material', 'compatible_device', ...
    data_type       VARCHAR NOT NULL CHECK (data_type IN ('text', 'number', 'enum', 'boolean')),
    unit            VARCHAR,                          -- SI unit when numeric: cm, g, ml
    storage         VARCHAR NOT NULL CHECK (storage IN ('column', 'eav'))  -- where the value lives
);

CREATE TABLE category_attribute (                    -- which attributes a leaf category requires or allows
    category_id     VARCHAR NOT NULL REFERENCES category (category_id),
    attribute_code  VARCHAR NOT NULL REFERENCES attribute (attribute_code),
    is_required     BOOLEAN NOT NULL,
    PRIMARY KEY (category_id, attribute_code)
);

CREATE TABLE product (                               -- parent product: what a shopper thinks of as "one item"
    product_id    VARCHAR PRIMARY KEY,
    title         VARCHAR NOT NULL,
    brand_id      INTEGER REFERENCES brand (brand_id),
    category_id   VARCHAR NOT NULL REFERENCES category (category_id),
    gender        VARCHAR CHECK (gender IN ('men', 'women', 'unisex', 'kids')),
    description   VARCHAR,                            -- PostgreSQL: TEXT
    language      VARCHAR(2) NOT NULL DEFAULT 'en'
);

CREATE TABLE variant (                               -- sellable SKU
    sku             VARCHAR PRIMARY KEY,
    product_id      VARCHAR NOT NULL REFERENCES product (product_id),
    title           VARCHAR NOT NULL,
    colour          VARCHAR CHECK (colour IN ('black','white','grey','silver','gold','brown','beige','red','pink',
                                              'orange','yellow','green','blue','purple','multicolour','clear')),
    size            VARCHAR,
    material        VARCHAR,
    length_cm       DECIMAL(9, 2) CHECK (length_cm > 0),
    width_cm        DECIMAL(9, 2) CHECK (width_cm > 0),
    height_cm       DECIMAL(9, 2) CHECK (height_cm > 0),
    weight_g        DECIMAL(11, 2) CHECK (weight_g > 0),
    net_qty         DECIMAL(11, 2) CHECK (net_qty > 0),
    net_unit        VARCHAR CHECK (net_unit IN ('g', 'ml')),
    capacity_ml     DECIMAL(11, 2) CHECK (capacity_ml > 0),
    pack_count      INTEGER CHECK (pack_count > 0),
    gtin            VARCHAR(14),
    listing_status  VARCHAR NOT NULL CHECK (listing_status IN ('active', 'held for review')),
    quality_score   DECIMAL(5, 4) CHECK (quality_score BETWEEN 0 AND 1),
    CHECK ((net_qty IS NULL) = (net_unit IS NULL))
);

CREATE TABLE price (                                 -- history-ready: one row per SKU and start date
    sku         VARCHAR NOT NULL REFERENCES variant (sku),
    currency    VARCHAR(3) NOT NULL DEFAULT 'USD',
    amount      DECIMAL(10, 2) NOT NULL CHECK (amount >= 0),
    valid_from  DATE NOT NULL,
    PRIMARY KEY (sku, valid_from)
);

CREATE TABLE inventory (
    sku         VARCHAR PRIMARY KEY REFERENCES variant (sku),
    stock_qty   INTEGER NOT NULL CHECK (stock_qty >= 0),
    in_stock    BOOLEAN NOT NULL,
    CHECK (in_stock = (stock_qty > 0))
);

CREATE TABLE variant_attribute (                     -- entity-attribute-value, for the long tail only
    sku             VARCHAR NOT NULL REFERENCES variant (sku),
    attribute_code  VARCHAR NOT NULL REFERENCES attribute (attribute_code),
    value_text      VARCHAR,
    value_num       DOUBLE,
    PRIMARY KEY (sku, attribute_code),
    CHECK (value_text IS NOT NULL OR value_num IS NOT NULL)
);

CREATE TABLE source_listing (                        -- lineage: every raw listing and the SKU it became
    listing_sku     VARCHAR PRIMARY KEY,
    source          VARCHAR NOT NULL CHECK (source IN ('abo', 'off', 'mkb')),
    source_id       VARCHAR NOT NULL,
    canonical_sku   VARCHAR NOT NULL REFERENCES variant (sku),
    match_method    VARCHAR                           -- NULL = itself; 'gtin', 'brand+model number', 'title similarity'
);

CREATE INDEX idx_category_parent   ON category (parent_id);
CREATE INDEX idx_product_category  ON product (category_id);
CREATE INDEX idx_product_brand     ON product (brand_id);
CREATE INDEX idx_variant_product   ON variant (product_id);
CREATE INDEX idx_variant_colour    ON variant (colour);
CREATE INDEX idx_vattr_code_value  ON variant_attribute (attribute_code, value_text);
CREATE INDEX idx_source_canonical  ON source_listing (canonical_sku);
-- PostgreSQL: same DDL; DOUBLE -> DOUBLE PRECISION; add a GIN index if variant_attribute moves to JSONB.
