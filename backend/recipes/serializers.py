import base64

from django.core.files.base import ContentFile
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from recipes.models import (FavoriteList, Ingredient, Recipe, RecipeIngredient,
                            ShoppingList, Tag)
from users.serializers import CustomUserSerializer


class Base64ImageField(serializers.ImageField):
    """Кодирование изображения в base64."""
    def to_internal_value(self, data):
        if isinstance(data, str) and data.startswith('data:image'):
            format, imgstr = data.split(';base64,')
            ext = format.split('/')[-1]
            data = ContentFile(base64.b64decode(imgstr), name='photo.' + ext)
        return super().to_internal_value(data)


class TagSerializer(serializers.ModelSerializer):
    """Теги."""
    class Meta:
        model = Tag
        fields = '__all__'
        read_only_fields = ('__all__',)


class IngredientSerializer(serializers.ModelSerializer):
    """Ингредиенты."""
    class Meta:
        model = Ingredient
        fields = '__all__'


class RecipeIngredientSerializer(serializers.ModelSerializer):
    """Подробное описание ингредиентов в рецепте."""
    name = serializers.CharField(
        source='ingredient.name', read_only=True)
    id = serializers.PrimaryKeyRelatedField(
        source='ingredient.id', read_only=True)
    measurement_unit = serializers.CharField(
        source='ingredient.measurement_unit', read_only=True)

    class Meta:
        model = RecipeIngredient
        fields = ('id', 'name', 'measurement_unit', 'amount')


class AddIngredientSerializer(serializers.ModelSerializer):
    """Добавление ингредиента при создании рецепта."""
    id = serializers.PrimaryKeyRelatedField(
        queryset=Ingredient.objects.all(),
        source='ingredient')

    class Meta:
        model = RecipeIngredient
        fields = ('id', 'amount')


class RecipeSerializer(serializers.ModelSerializer):
    """Cоздание рецепта."""
    author = CustomUserSerializer(read_only=True)
    image = Base64ImageField()
    ingredients = AddIngredientSerializer(many=True)

    class Meta:
        model = Recipe
        fields = ('id', 'tags', 'author', 'ingredients',
                  'name', 'image', 'text', 'cooking_time')

    def validate(self, data):
        list_ingr = [item['ingredient'] for item in data['ingredients']]
        all_ingredients = len(list_ingr)
        distinct_ingredients = len(set(list_ingr))

        if all_ingredients != distinct_ingredients:
            raise ValidationError(
                {'error': 'Ингредиенты должны быть уникальными'}
            )
        return data

    def get_ingredients(self, recipe, ingredients):
        RecipeIngredient.objects.bulk_create(
            RecipeIngredient(
                recipe=recipe,
                ingredient=ingredient.get('ingredient'),
                amount=ingredient.get('amount')
            ) for ingredient in ingredients)

    def create(self, validated_data):
        user = self.context.get('request').user
        tags = validated_data.pop('tags')
        ingredients = validated_data.pop('ingredients')
        recipe = Recipe.objects.create(author=user,
                                       **validated_data)
        recipe.tags.set(tags)
        self.get_ingredients(recipe, ingredients)
        return recipe

    def update(self, instance, validated_data):
        tags = validated_data.pop('tags')
        ingredients = validated_data.pop('ingredients')
        RecipeIngredient.objects.filter(recipe=instance).delete()
        instance.tags.set(tags)
        self.get_ingredients(instance, ingredients)
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        context = {'request': self.context.get('request')}
        return GetRecipeSerializer(instance, context=context).data


class GetRecipeSerializer(serializers.ModelSerializer):
    """Полная информация о рецепте."""
    tags = TagSerializer(many=True)
    author = CustomUserSerializer(read_only=True)
    ingredients = RecipeIngredientSerializer(read_only=True, many=True,
                                             source='recipe_ingredient')
    is_favorited = serializers.SerializerMethodField(read_only=True)
    is_in_shopping_cart = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Recipe
        fields = ('id', 'tags', 'author', 'ingredients',
                  'is_favorited', 'is_in_shopping_cart',
                  'name', 'image', 'text', 'cooking_time')

    def get_is_favorited(self, object):
        user = self.context.get('request').user
        if user.is_authenticated:
            return object.favorite.filter(user=user).exists()
        return False

    def get_is_in_shopping_cart(self, object):
        user = self.context.get('request').user
        if user.is_authenticated:
            return object.shopping_cart.filter(user=user).exists()
        return False


class FavoriteSerializer(serializers.ModelSerializer):
    """Добавление и удаление рецепта в избранном."""
    class Meta:
        model = FavoriteList
        fields = ('user', 'recipe')

    def validate(self, data):
        user = data.get('user')
        recipe = data.get('recipe')
        if self.Meta.model.objects.filter(user=user, recipe=recipe).exists():
            raise ValidationError(
                {'error': 'Этот рецепт уже добавлен'}
            )
        return data

    def to_representation(self, instance):
        context = {'request': self.context.get('request')}
        return RecipeInfoSerializer(instance.recipe, context=context).data


class ShoppingCartSerializer(FavoriteSerializer):
    """Добавление и удаление рецепта в списке покупок."""
    class Meta(FavoriteSerializer.Meta):
        model = ShoppingList


class RecipeInfoSerializer(serializers.ModelSerializer):
    """Краткая информация о рецепте."""
    class Meta:
        model = Recipe
        fields = ('id', 'name', 'image', 'cooking_time')
