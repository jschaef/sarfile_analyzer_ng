#!/usr/bin/python3
import time
import altair as alt
import dataframe_funcs_pl as ddf
import pandas as pd

my_tz = time.tzname[0]

# Lazy initialization of data transformer to avoid loading at import time
_transformer_initialized = False

def _initialize_data_transformer():
    """Initialize data transformer only when needed (lazy loading)
    
    Using VegaFusion transformer which does server-side data transformations.
    This significantly reduces browser memory by pre-aggregating data before
    sending to the browser.
    
    Falls back to JSON transformer if VegaFusion is not available, and finally
    to disable_max_rows as last resort.
    """
    global _transformer_initialized
    if not _transformer_initialized:
        # https://altair-viz.github.io/user_guide/faq.html#maxrowserror-how-can-i-plot-large-datasets
        # Try VegaFusion first - most powerful memory optimization
        try:
            import vegafusion as vf
            alt.data_transformers.enable('vegafusion')
            print("✓ Using VegaFusion data transformer for memory optimization")
        except (ImportError, Exception):
            # Fallback to JSON transformer
            try:
                alt.data_transformers.enable('json')
                print("✓ Using JSON data transformer (VegaFusion not available)")
            except Exception:
                # Last resort: disable max rows
                alt.data_transformers.disable_max_rows()
                print("✓ Using disable_max_rows transformer (fallback)")
        
        _transformer_initialized = True

def sample_dataframe_for_viz(df, max_rows=5000):
    """Sample large dataframes to reduce memory usage while preserving distribution.
    
    For very large datasets (>100k rows), uses more aggressive sampling.
    
    Args:
        df: DataFrame (Pandas or Polars)
        max_rows: Maximum rows to keep (default: 5000)
    
    Returns:
        Sampled DataFrame of the same type as input
    """
    df_len = len(df)
    
    # Aggressive sampling for very large datasets
    if df_len > 100000:
        max_rows = min(max_rows, 2000)  # Cap at 2000 for huge files
    elif df_len > 50000:
        max_rows = min(max_rows, 3000)  # Cap at 3000 for large files
    
    if df_len <= max_rows:
        return df
    
    # Check if Polars or Pandas
    if hasattr(df, 'sample'):  # Both have sample method
        if 'polars' in str(type(df).__module__):
            # Polars sampling
            return df.sample(n=max_rows, seed=42)
        else:
            # Pandas sampling
            return df.sample(n=max_rows, random_state=42).sort_index()
    return df

def draw_single_chart_v1(
    df,
    property,
    restart_headers,
    os_details,
    width,
    hight,
    ylabelpadd=10,
    font_size=None,
    title=None,
):
    _initialize_data_transformer()
    # Sample large datasets to reduce memory usage
    df = sample_dataframe_for_viz(df, max_rows=5000)
    # df['date'] = df['date'].dt.tz_localize('UTC', ambiguous=True)
    df["date_utc"] = df["date"].dt.tz_localize("UTC")
    rule_field, z_field, y_pos = create_reboot_rule(
        df, property, restart_headers, os_details
    )

    if "metric" in df.columns:
        color_item = "metric"
    else:
        color_item = "file"

    nearest = alt.selection_point(
        name="nearest_single_v1",
        nearest=True,
        on="mouseover",
        fields=[
            "date_utc",
        ],
        empty=False,
    )

    selectors = (
        alt.Chart(df)
        .mark_point()
        .encode(
            alt.X(
                "utchoursminutes(date_utc)",
                type="temporal",
                scale=alt.Scale(type="utc"),
                title="",
            ),
            opacity=alt.value(0),
        )
        .add_params(nearest)
    )

    c = (
        alt.Chart(df)
        .mark_line(point=False, interpolate="linear")
        .encode(
            alt.X(
                "utchoursminutes(date_utc)",
                type="temporal",
                scale=alt.Scale(zero=True),
                axis=alt.Axis(domain=True, labelBaseline="line-top", title="time"),
            ),
            alt.Y(
                property,
                scale=alt.Scale(zero=True),
                axis=alt.Axis(
                    labelPadding=ylabelpadd,
                    titlePadding=5,
                ),
            ),
            color=alt.Color(f"{color_item}:N", legend=None),
        )
        .properties(width=width, height=hight, title=title)
    )

    legend = (
        alt.Chart(df)
        .mark_point()
        .encode(
            y=alt.Y(f"{color_item}:N", axis=alt.Axis(orient="right"), ),
            color=alt.Color(
                f"{color_item}:N",
            ),
        )
    )

    rules = (
        alt.Chart(df)
        .mark_rule(color="gray", interpolate="linear")
        .encode(
            alt.X("utchoursminutes(date_utc)", type="temporal"),
        )
        .transform_filter(nearest)
    )

    points = c.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    )

    text = c.mark_text(align="left", dx=5, dy=-5).encode(
        text=alt.condition(nearest, f"{property}:Q", alt.value(" "), format=".2f")
    )

    reboot_text = return_reboot_text(z_field, y_pos, col="dummy", col_value="dummy")
    if reboot_text:
        reboot_text = reboot_text.encode(color=alt.Color("dummy:N", legend=None))

    for rule in rule_field:
        rule = rule.encode(color=alt.Color("dummy:N", legend=None))
        c += rule

    if reboot_text:
        c += reboot_text
    mlayer = alt.layer(
        c,
        selectors,
        points,
        rules,
        text,
    ).interactive()
    result = mlayer | legend
    if font_size is not None:
        result = result.configure_axis(
            labelFontSize=font_size,
            titleFontSize=font_size,
        ).configure_title(fontSize=font_size)
    return result


def create_reboot_rule(
    df,
    property,
    restart_headers,
    os_details,
    col=None,
    col_value=12,
    utc_type="utchoursminutes",
):
    y_pos = df[property].max() / 2
    rule_field = []
    z_field = []
    for header in restart_headers:
        xval = header.split()[-1]
        date_str, _ = ddf.format_date(os_details)
        z = pd.to_datetime(f"{date_str} {xval}", format="mixed")
        z = z.replace(tzinfo=None).replace(tzinfo=pd.Timestamp('2000-01-01', tz='UTC').tzinfo)
        z_field.append(z)
        if col is None:
            col = "dummy"
        mdf = pd.DataFrame({"x": [z], col: col_value})
        rule = (
            alt.Chart(mdf)
            .mark_rule(color="orange", strokeWidth=1, strokeDash=[5, 5], interpolate="linear")
            .encode(
                x=alt.X(
                    # "utcdayhoursminutes(x)", type="temporal", axis=alt.Axis(title="date")
                    f"{utc_type}(x)",
                    type="temporal",
                    axis=alt.Axis(),
                    stack=False
                ),
                # size=alt.value(2),
                # strokeDash=(alt.value([5, 5])),
            )
        )

        rule_field.append(rule)
    return rule_field, z_field, y_pos


def return_reboot_text(
    z_field, y_pos, col=None, col_value=None, utc_type="utchoursminutes"
):
    if z_field:
        mdf = pd.DataFrame({"date": z_field, "y": y_pos, col: col_value})
        reboot_text = (
            alt.Chart(mdf)
            .mark_text(text="RESTART", angle=90, color="black", fontSize=12)
            .encode(
                alt.X(f"{utc_type}(date)", type="temporal"),
            )
        )
    else:
        reboot_text = None
    return reboot_text

def overview_v1(
    df, restart_headers, os_details, font_size=None, width=None, height=None, title=None
):
    _initialize_data_transformer()
    # Sample large datasets to reduce memory usage
    df = sample_dataframe_for_viz(df, max_rows=5000)
    df["date_utc"] = df["date"].dt.tz_localize("UTC")
    rule_field, z_field, y_pos = create_reboot_rule(
        df, "y", restart_headers, os_details
    )

    # Create selections with unique names
    selection_new = alt.selection_point(name="selection_overview_v1", fields=["metrics"])
    pan_zoom = alt.selection_interval(name="pan_zoom_v1", bind='scales')

    color_x = alt.condition(
        selection_new, alt.Color("metrics:N", legend=None), alt.value("")
    )

    opacity_x = alt.condition(selection_new, alt.value(1.0), alt.value(0))
    line = (
        alt.Chart(df)
        .encode(
            alt.X("utchoursminutes(date_utc)", type="temporal", title="time"),
            alt.Y("y:Q"),
            opacity=opacity_x,
        )
        .properties(width=width, height=height, title=title)
    )

    final_line = (
        line.mark_line(strokeWidth=2).add_params(selection_new, pan_zoom).encode(color=color_x)
    )

    legend = (
        alt.Chart(df)
        .mark_point()
        .encode(y=alt.Y("metrics:N", axis=alt.Axis(orient="right")), color=color_x)
    )

    nearest = alt.selection_point(
        name="nearest_overview_v1",
        nearest=True, on="mouseover", fields=["date"], empty=False
    )

    selectors = (
        alt.Chart(df)
        .mark_point()
        .encode(
            alt.X(
                "utchoursminutes(date_utc)",
                type="temporal",
                scale=alt.Scale(type="utc"),
                title="",
            ),
            opacity=alt.value(0),
        )
        .add_params(nearest)
    )

    rules = (
        alt.Chart(df)
        .mark_rule(color="gray")
        .encode(
            alt.X("utchoursminutes(date_utc)", type="temporal"),
        )
        .transform_filter(nearest)
    )

    # xpoints = alt.Chart(df).mark_point().encode(
    #     alt.X('utchoursminutes(date_utc)', type='temporal'),
    #     alt.Y('y:Q',),
    #     opacity=alt.condition(selection_new, alt.value(1), alt.value(0)),
    #     color=color_x
    # ).transform_filter(
    #     nearest
    # )

    tooltip_text = line.mark_text(
        align="left",
        dx=-30,
        dy=-15,
        fontSize=font_size,
        lineBreak="\n",
    ).encode(
        text=alt.condition(
            nearest,
            alt.Text("y:Q", format=".2f"),
            alt.value(" "),
        ),
        opacity=alt.condition(selection_new, alt.value(1), alt.value(0)),
        color=color_x,
    )
    for rule in rule_field:
        rule = rule.encode(color=alt.Color("dummy:N", legend=None))

        final_line += rule
    reboot_text = return_reboot_text(z_field, y_pos, col="dummy", col_value="dummy")

    if reboot_text:
        reboot_text = reboot_text.encode(color=alt.Color("dummy:N", legend=None))

        final_line += reboot_text

    mlayer = alt.layer(final_line, selectors, rules, tooltip_text)
    # mlayer = mlayer|legend
    mlayer = alt.hconcat(mlayer, legend).configure_concat(spacing=50)
    result = mlayer.configure_axis(
        labelFontSize=font_size, titleFontSize=font_size
    )
    if font_size is not None:
        result = result.configure_title(fontSize=font_size)
    return result


def overview_v3(
    collect_field, reboot_headers, width, height, lsel, font_size, title=None
):
    _initialize_data_transformer()
    color_item = lsel
    b_df = pd.DataFrame()
    z_fields = []
    rule_fields = []
    y_pos = 0
    for data in collect_field:
        df = data[0]
        # Sample large datasets to reduce memory usage
        df = sample_dataframe_for_viz(df, max_rows=5000)
        if not df.empty:
            df["date_utc"] = df["date"].dt.tz_localize("UTC")
            property = data[1]
            filename = df["file"].iloc[0]
            for header in reboot_headers:
                if header[0]:
                    hostname = header[1].split()[2].strip("()")
                    date = header[1].split()[3]
                    if hostname in filename and date in filename:
                        rule_field, z_field, y_pos = create_reboot_rule(
                            df,
                            property,
                            header[0],
                            header[1],
                            col=color_item,
                            col_value=filename,
                        )
                        rule_fields.append(rule_field)
                        z_fields.append([z_field, filename])

        b_df = pd.concat([b_df, df], ignore_index=False)
    
    # Create pan/zoom selection
    pan_zoom = alt.selection_interval(name="pan_zoom_v3", bind='scales')
    
    nearest = alt.selection_point(
        name="nearest_v3",
        nearest=True, on="mouseover", fields=["date_utc"], empty=False
    )

    selectors = (
        alt.Chart(b_df)
        .mark_point()
        .encode(
            alt.X(
                "utchoursminutes(date_utc)",
                type="temporal",
                scale=alt.Scale(type="utc"),
                title="",
            ),
            opacity=alt.value(0),
        )
        .add_params(nearest)
    )

    selection = alt.selection_point(
        name="selection_v3",
        fields=[color_item],
    )
    color_x = alt.condition(
        selection,
        alt.Color(f"{color_item}:N", legend=None),
        alt.value(
            "",
        ),
    )
    opacity_x = alt.condition(selection, alt.value(1.0), alt.value(0))

    c = (
        alt.Chart(b_df)
        .mark_line(point=False, interpolate="natural")
        .encode(
            alt.X(
                "utchoursminutes(date_utc)",
                type="temporal",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(domain=True, labelBaseline="line-top", title="time"),
            ),
            # alt.Y(property, type='quantitative', scale=alt.Scale(zero=False),
            alt.Y(
                property,
                scale=alt.Scale(zero=False),
                axis=alt.Axis(
                    titlePadding=5,
                ),
            ),
            opacity=opacity_x,
        )
        .properties(width=width, height=height, title=title)
    )

    final_img = c.mark_line(strokeWidth=2).add_params(selection, pan_zoom).encode(color=color_x)

    rules = (
        alt.Chart(b_df)
        .mark_rule(color="gray")
        .encode(
            alt.X("utchoursminutes(date_utc)", type="temporal"),
        )
        .transform_filter(nearest)
    )

    legend = (
        alt.Chart(b_df)
        .mark_point()
        .encode(y=alt.Y("file:N", axis=alt.Axis(orient="right")), color=color_x)
    )

    xpoints = c.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0)), color=color_x
    )

    text_kwargs = {
        "align": "left",
        "dx": -10,
        "dy": -25,
        "lineBreak": "\n",
    }
    if font_size is not None and isinstance(font_size, (int, float)):
        text_kwargs["fontSize"] = font_size
    
    tooltip_text = c.mark_text(**text_kwargs).encode(
        text=alt.condition(
            nearest,
            alt.Text(f"{property}:Q", format=".2f"),
            alt.value(" "),
        ),
        opacity=alt.condition(selection, alt.value(1), alt.value(0)),
        color=color_x,
    )

    if z_fields:
        while rule_fields:
            rule_field = rule_fields.pop()
            while rule_field:
                rule = rule_field.pop()
                rule = rule.encode(
                    opacity=alt.condition(selection, alt.value(1), alt.value(0)),
                    color=color_x,
                )
                final_img += rule
        while z_fields:
            t_field = z_fields.pop()
            z_field = t_field[0]
            filename = t_field[1]
            reboot_text = return_reboot_text(
                z_field, y_pos, col=color_item, col_value=filename
            )
            reboot_text = reboot_text.encode(
                opacity=alt.condition(selection, alt.value(1), alt.value(0)),
                color=color_x,
            )
            final_img += reboot_text
        mlayer = alt.layer(
            final_img,
            selectors,
            rules,
            xpoints,
            tooltip_text,
        )
    else:
        mlayer = alt.layer(
            final_img, selectors, rules, xpoints, tooltip_text
        )
    result = mlayer | legend
    if font_size is not None and isinstance(font_size, (int, float)):
        result = result.configure_axis(
            labelFontSize=font_size, titleFontSize=font_size
        ).configure_title(fontSize=font_size)
    return result


def overview_v4(collect_field, reboot_headers, width, height, font_size):
    _initialize_data_transformer()
    color_item = "metric"
    b_df = pd.DataFrame()
    property = "y"  # Initialize with the melted column name
    filename = ""  # Initialize filename to avoid unbound variable
    z_field = []
    rule_field = []
    for data in collect_field:
        df = data[0]
        # Sample large datasets to reduce memory usage
        df = sample_dataframe_for_viz(df, max_rows=5000)
        property = data[1]
        filename = df["file"].iloc[0]
        for header in reboot_headers:
            if header[0]:
                hostname = header[1].split()[2].strip("()")
                date = header[1].split()[3]
                if hostname in filename and date in filename:
                    rule_field, z_field, y_pos = create_reboot_rule(
                        df,
                        property,
                        header[0],
                        header[1],
                        col=color_item,
                        col_value=filename,
                    )

        b_df[property] = df[property]

    b_df = b_df.reset_index().melt("date", var_name="metrics", value_name="y")
    b_df["date_utc"] = pd.to_datetime(b_df["date"]).dt.tz_localize("UTC")

    nearest = alt.selection_point(
        name="nearest_v4",
        nearest=True, on="mouseover", fields=["date_utc"], empty=False
    )

    selectors = (
        alt.Chart(b_df)
        .mark_point()
        .encode(
            alt.X(
                "utchoursminutes(date_utc)",
                type="temporal",
                scale=alt.Scale(type="utc"),
                title="",
            ),
            opacity=alt.value(0),
        )
        .add_params(nearest)
    )

    selection = alt.selection_point(
        name="selection_v4",
        fields=["metrics"],
    )
    pan_zoom = alt.selection_interval(name="pan_zoom_v4", bind='scales')
    
    color_x = alt.condition(
        selection,
        alt.Color("metrics:N", legend=None),
        alt.value(
            "",
        ),
    )

    opacity_x = alt.condition(selection, alt.value(1.0), alt.value(0))

    # line = alt.Chart(b_df).encode(
    line = (
        alt.Chart(b_df)
        .mark_line(point=False, interpolate="natural")
        .encode(
            alt.X("utchoursminutes(date_utc)", type="temporal", title="time"),
            alt.Y("y:Q"),
            opacity=opacity_x,
        )
        .properties(width=width, height=height)
    )

    final_line = (
        line.mark_line(strokeWidth=2).add_params(selection, pan_zoom).encode(color=color_x)
    )

    rules = (
        alt.Chart(b_df)
        .mark_rule(color="gray")
        .encode(
            alt.X("utchoursminutes(date_utc)", type="temporal"),
        )
        .transform_filter(nearest)
    )

    legend = (
        alt.Chart(b_df)
        .mark_point()
        .encode(y=alt.Y("metrics:N", axis=alt.Axis(orient="right")), color=color_x)
    )

    xpoints = line.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0)), color=color_x
    )

    text_kwargs = {
        "align": "left",
        "dx": -10,
        "dy": -25,
        "lineBreak": "\n",
    }
    if font_size is not None:
        text_kwargs["fontSize"] = font_size
    
    tooltip_text = line.mark_text(**text_kwargs).encode(
        text=alt.condition(
            nearest,
            alt.Text("y:Q", format=".2f"),
            alt.value(" "),
        ),
        opacity=alt.condition(selection, alt.value(1), alt.value(0)),
        color=color_x,
    )

    if z_field:
        while rule_field:
            rule = rule_field.pop()
            rule = rule.encode(color="filename:N")
            final_line += rule

        reboot_text = return_reboot_text(
            z_field, y_pos, col=color_item, col_value=filename
        )
        if reboot_text is not None:
            reboot_text = reboot_text.encode(
                color="filename:N",
            )
            final_line += reboot_text
        
        mlayer = alt.layer(
            final_line, selectors, rules, tooltip_text, xpoints
        )
    else:
        mlayer = alt.layer(
            final_line, selectors, rules, xpoints, tooltip_text
        )
    return (mlayer | legend).configure_axis(
        labelFontSize=font_size, titleFontSize=font_size
    )


def overview_v5(
    b_df,
    property,
    filename,
    reboot_headers,
    width,
    height,
    lsel,
    font_size,
    os_details,
    title=None,
):
    _initialize_data_transformer()
    # Sample large datasets to reduce memory usage
    b_df = sample_dataframe_for_viz(b_df, max_rows=5000)
    color_item = lsel
    z_field = []
    rule_field = []
    y_pos = 0
    b_df = b_df.with_columns(b_df["date"].dt.replace_time_zone("UTC").alias("date_utc"))

    for header in reboot_headers:
        rule_field, z_field, y_pos = create_reboot_rule(
            b_df,
            property,
            header,
            os_details,
            col=color_item,
            col_value=filename,
        )

    nearest = alt.selection_point(
        name="nearest_v5",
        nearest=True, on="mouseover", fields=["date_utc"], empty=False
    )

    # here the wrong date (localtime) is used, but it is not visible
    selectors = (
        alt.Chart(b_df)
        .mark_point()
        .encode(
            alt.X(
                "utchoursminutes(date_utc)",
                type="temporal",
                scale=alt.Scale(type="utc"),
                title="",
            ),
            opacity=alt.value(0),
        )
        .add_params(nearest)
    )

    selection = alt.selection_point(
        name="selection_v5",
        fields=[lsel],
    )
    pan_zoom = alt.selection_interval(name="pan_zoom_v5", bind='scales')
    
    color_x = alt.condition(
        selection,
        alt.Color(f"{lsel}:N", legend=None),
        alt.value(
            "",
        ),
    )

    opacity_x = alt.condition(selection, alt.value(1.0), alt.value(0))

    line = (
        alt.Chart(b_df)
        .mark_line(point=False, interpolate="natural")
        .encode(
            alt.X(
                "utchoursminutes(date_utc)",
                type="temporal",
                title="time",
                scale=alt.Scale(
                    zero=False,
                    nice=True,
                    type="utc",
                ),
            ),
            alt.Y(f"{property}:Q"),
            opacity=opacity_x,
        )
        .properties(
            width=width,
            height=height,
            title=title,
        )
    )

    final_line = (
        line.mark_line(strokeWidth=2).add_params(selection, pan_zoom).encode(color=color_x)
    )
    rules = (
        alt.Chart(b_df)
        .mark_rule(color="gray")
        .encode(
            alt.X("utchoursminutes(date_utc)", type="temporal"),
        )
        .transform_filter(nearest)
    )

    legend = (
        alt.Chart(b_df)
        .mark_point()
        .encode(
            y=alt.Y(f"{color_item}:N", axis=alt.Axis(orient="right")), color=color_x
        )
    )

    xpoints = line.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0)), color=color_x
    )

    text_kwargs = {
        "align": "left",
        "dx": -10,
        "dy": -25,
        "lineBreak": "\n",
    }
    if font_size is not None:
        text_kwargs["fontSize"] = font_size
    
    tooltip_text = line.mark_text(**text_kwargs).encode(
        text=alt.condition(
            nearest,
            alt.Text(f"{property}:Q", format=".2f"),
            alt.value(" "),
        ),
        opacity=alt.condition(selection, alt.value(1), alt.value(0)),
        color=color_x,
    )
    if z_field:
        while rule_field:
            rule = rule_field.pop()
            rule = rule.encode(color=f"{lsel}:N")
            final_line += rule

        reboot_text = return_reboot_text(
            z_field, y_pos, col=color_item, col_value=filename
        )
        if reboot_text:
            reboot_text = reboot_text.encode(
                color="filename:N",
            )
            mlayer = alt.layer(
                final_line, selectors, rules, tooltip_text, reboot_text, xpoints
            )
        else:
            mlayer = alt.layer(
                final_line, selectors, rules, tooltip_text, xpoints
            )
    else:
        mlayer = alt.layer(
            final_line, selectors, rules, xpoints, tooltip_text
        )
    return (
        (mlayer | legend)
        .configure_axis(labelFontSize=font_size, titleFontSize=font_size)
        .configure_title(fontSize=font_size)
    )


def overview_v6(collect_field, reboot_headers, width, height, font_size, title=None):
    _initialize_data_transformer()
    color_item = "date_short"
    b_df = pd.DataFrame()
    z_fields = []
    rule_fields = []
    y_pos = 0
    for data in collect_field:
        df = data[0]
        # Sample large datasets to reduce memory usage
        df = sample_dataframe_for_viz(df, max_rows=5000)
        if not df.empty:
            df["date_utc"] = df["date"].dt.tz_localize("UTC")
            property = data[1]
            filename = df["file"].iloc[0]
            for header in reboot_headers:
                if header[0]:
                    rule_field, z_field, y_pos = create_reboot_rule(
                        df,
                        property,
                        header[0],
                        header[1],
                        col=color_item,
                        utc_type="utcdayhoursminutes",
                    )
                    rule_fields.append(rule_field)
                    z_fields.append([z_field, filename])

        b_df = pd.concat([b_df, df], ignore_index=False)
    b_df["date_short"] = b_df["date"].dt.floor('1d')
    nearest = alt.selection_point(
        nearest=True, on="mouseover", fields=["date"], empty=False
    )

    selectors = (
        alt.Chart(b_df)
        .mark_point()
        .encode(
            alt.X(
                "utcdayhoursminutes(date)",
                type="temporal",
                scale=alt.Scale(
                    type="utc",
                ),
                title="",
            ),
            opacity=alt.value(0),
        )
        .add_params(nearest)
    )

    selection = alt.selection_point(
        name="selection_v6",
        fields=[color_item],
    )
    pan_zoom = alt.selection_interval(name="pan_zoom_v6", bind='scales')
    
    color_x = alt.condition(
        selection,
        alt.Color(f"{color_item}:N", legend=None),
        alt.value(
            "",
        ),
    )
    opacity_x = alt.condition(selection, alt.value(1.0), alt.value(0))
    c = (
        alt.Chart(b_df)
        .mark_line(point=False, interpolate="natural")
        .encode(
            alt.X(
                "utcdayhoursminutes(date):T",
                scale=alt.Scale(
                    zero=False,
                    nice=True,
                    type="utc",
                ),
                axis=alt.Axis(
                    domain=True,
                    labelBaseline="line-top",
                ),
            ),
            # check this:
            # scale=alt.Scale(domain=['2012-01-01T00:00:00', '2012-01-02T00:00:00'])
            # alt.Y(property, type='quantitative', scale=alt.Scale(zero=False),
            alt.Y(
                property,
                scale=alt.Scale(zero=True),
                axis=alt.Axis(
                    titlePadding=5,
                ),
            ),
            opacity=opacity_x,
        )
        .properties(width=width, height=height, title=title)
    )

    final_img = c.mark_line(strokeWidth=2).add_params(selection, pan_zoom).encode(color=color_x)

    rules = (
        alt.Chart(b_df)
        .mark_rule(color="gray")
        .encode(
            alt.X("utcdayhoursminutes(date_utc)", type="temporal"),
        )
        .transform_filter(nearest)
    )

    legend = (
        alt.Chart(b_df)
        .mark_point()
        .encode(y=alt.Y("date", axis=alt.Axis(orient="right")), color=color_x)
    )

    xpoints = c.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0)), color=color_x
    )

    text_kwargs = {
        "align": "left",
        "dx": -10,
        "dy": -25,
        "lineBreak": "\n",
    }
    if font_size is not None:
        text_kwargs["fontSize"] = font_size
    
    tooltip_text = c.mark_text(**text_kwargs).encode(
        text=alt.condition(
            nearest,
            alt.Text(f"{property}:Q", format=".2f"),
            alt.value(" "),
        ),
        opacity=alt.condition(selection, alt.value(1), alt.value(0)),
        color=color_x,
    )

    if z_fields:
        while rule_fields:
            rule_field = rule_fields.pop()
            while rule_field:
                rule = rule_field.pop()
                rule = rule.encode(
                    opacity=alt.condition(selection, alt.value(1), alt.value(0)),
                    color=color_x,
                )
                final_img += rule
        while z_fields:
            t_field = z_fields.pop()
            z_field = t_field[0]
            filename = t_field[1]
            reboot_text = return_reboot_text(
                z_field,
                y_pos,
                col=color_item,
                col_value=filename,
                utc_type="utcdayhoursminutes",
            )
            reboot_text = reboot_text.encode(
                opacity=alt.condition(selection, alt.value(1), alt.value(0)),
                color=color_x,
            )
            final_img += reboot_text
        mlayer = alt.layer(
            final_img,
            selectors,
            rules,
            xpoints,
            tooltip_text,
        )
    else:
        mlayer = alt.layer(
            final_img, selectors, rules, xpoints, tooltip_text
        )
    return (
        (mlayer | legend)
        .configure_axis(labelFontSize=font_size, titleFontSize=font_size)
        .configure_title(fontSize=font_size)
    )
