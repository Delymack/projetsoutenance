from django.db import migrations, models


def ensure_user_recovery_columns(apps, schema_editor):
    user_model = apps.get_model('accounts', 'User')
    table = schema_editor.quote_name(user_model._meta.db_table)
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, user_model._meta.db_table
            )
        }

    fields = (
        ('avatar', models.CharField(max_length=100, blank=True, null=True)),
        ('code_recuperation_expire_le', models.DateTimeField(blank=True, null=True)),
        ('code_recuperation_hash', models.CharField(max_length=128, blank=True, default='')),
    )
    for name, field in fields:
        if name not in columns:
            user_model.add_to_class(name, field)
            schema_editor.add_field(user_model, field)
        elif name == 'code_recuperation_hash':
            schema_editor.execute(
                f'UPDATE {table} SET {schema_editor.quote_name(name)} = %s '
                f'WHERE {schema_editor.quote_name(name)} IS NULL',
                [''],
            )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_loginevent_appareil'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    ensure_user_recovery_columns,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='user',
                    name='avatar',
                    field=models.CharField(blank=True, max_length=100, null=True),
                ),
                migrations.AddField(
                    model_name='user',
                    name='code_recuperation_expire_le',
                    field=models.DateTimeField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='user',
                    name='code_recuperation_hash',
                    field=models.CharField(blank=True, default='', max_length=128),
                ),
            ],
        ),
    ]
